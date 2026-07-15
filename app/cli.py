"""コマンドライン（CLI）操作。

初期管理者の作成やマスタ初期投入など、画面が無い状態でも実行できる操作をまとめる。
使用例:
    flask create-admin        # 対話形式でシステム管理者を作成
    flask seed-masters        # 確度/区分/部門/カテゴリーの初期値を投入
"""
import getpass

import click
from flask import Flask

from .extensions import db
from .models import (User, Rank, Department, Kubun, Category, ProductCategory,
                     ROLE_SYSADMIN)


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--user-id", prompt="システム管理者のログインID", help="ログインID")
    @click.option("--name", prompt="氏名", help="表示名")
    def create_admin(user_id, name):
        """初期のシステム管理者アカウントを作成する。"""
        existing = db.session.get(User, user_id)
        if existing:
            click.echo(f"エラー: ログインID '{user_id}' は既に存在します。")
            return
        password = getpass.getpass("パスワード: ")
        password2 = getpass.getpass("パスワード（確認）: ")
        if password != password2:
            click.echo("エラー: パスワードが一致しません。")
            return
        if len(password) < 8:
            click.echo("エラー: パスワードは8文字以上にしてください。")
            return

        admin = User(user_id=user_id, name=name, role=ROLE_SYSADMIN,
                     is_active_flag=True, must_change_password=False)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"システム管理者 '{user_id}'（{name}）を作成しました。")

    @app.cli.command("seed-masters")
    def seed_masters():
        """確度・区分・部門・カテゴリーの初期値を投入する（既存があればスキップ）。"""
        # 確度ランク（'○' が実績＝受注確定）
        default_ranks = ["○", "A", "B", "C", "D", "E", "×"]
        for i, name in enumerate(default_ranks):
            if not Rank.query.filter_by(name=name).first():
                db.session.add(Rank(name=name, sort_order=i))

        # 区分（期初計画 / 新規）
        default_kubun = [("期初計画", True), ("新規", False)]
        for i, (name, is_plan) in enumerate(default_kubun):
            if not Kubun.query.filter_by(name=name).first():
                db.session.add(Kubun(name=name, is_plan=is_plan, sort_order=i))

        # 部門
        default_departments = [
            "第1営業部", "大阪支店", "名古屋営業所", "ﾈｯﾄﾜｰｸｿﾘｭｰｼｮﾝ部",
            "第2営業部", "新規事業開発室", "経営企画部",
        ]
        for i, name in enumerate(default_departments):
            if not Department.query.filter_by(name=name).first():
                db.session.add(Department(name=name, sort_order=i))
        db.session.flush()  # カテゴリーが部門IDを参照するため確定させる

        # 第2営業部のカテゴリー（まずはテスト部門として投入）
        dept2 = Department.query.filter_by(name="第2営業部").first()
        if dept2:
            dept2_categories = [
                ("Ri", "Ribbon Communications関連"),
                ("Or", "Oracle関連"),
                ("Au", "Audiocodes関連"),
                ("Kd", "関西電力"),
                ("NM", "マンション"),
                ("Ot", "その他案件"),
            ]
            for i, (code, name) in enumerate(dept2_categories):
                exists = Category.query.filter_by(
                    department_id=dept2.id, code=code).first()
                if not exists:
                    db.session.add(Category(department_id=dept2.id, code=code,
                                            name=name, sort_order=i))

            # 第2営業部の商品カテゴリ
            dept2_product_categories = [
                "GW-保守", "GW-運用", "GW-構築", "GW-販売", "音声-保守",
                "マンション", "その他",
            ]
            for i, name in enumerate(dept2_product_categories):
                exists = ProductCategory.query.filter_by(
                    department_id=dept2.id, name=name).first()
                if not exists:
                    db.session.add(ProductCategory(department_id=dept2.id,
                                                   name=name, sort_order=i))

        db.session.commit()
        click.echo("マスタ（確度・区分・部門・カテゴリー・商品カテゴリ）の初期値を投入しました。")
