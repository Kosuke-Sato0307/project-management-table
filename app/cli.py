"""コマンドライン（CLI）操作。

初期管理者の作成やマスタ初期投入など、画面が無い状態でも実行できる操作をまとめる。
使用例:
    flask create-admin        # 対話形式で初期管理者を作成
    flask seed-masters        # ステータス/確度ランクの初期値を投入
"""
import getpass

import click
from flask import Flask

from .extensions import db
from .models import User, Status, Rank


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    @click.option("--user-id", prompt="管理者のログインID", help="ログインID")
    @click.option("--name", prompt="氏名", help="表示名")
    def create_admin(user_id, name):
        """初期管理者アカウントを作成する。"""
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

        admin = User(user_id=user_id, name=name, role="admin",
                     is_active_flag=True, must_change_password=False)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        click.echo(f"管理者 '{user_id}'（{name}）を作成しました。")

    @app.cli.command("seed-masters")
    def seed_masters():
        """案件ステータス・確度ランクの初期値を投入する（既存があればスキップ）。"""
        default_statuses = ["進行中", "受注", "失注", "完了"]
        for i, name in enumerate(default_statuses):
            if not Status.query.filter_by(name=name).first():
                db.session.add(Status(name=name, sort_order=i))

        default_ranks = [
            ("A", "受注確実（目安 80%以上）"),
            ("B", "有望（目安 50%程度）"),
            ("C", "初期段階（目安 30%以下）"),
        ]
        for i, (name, note) in enumerate(default_ranks):
            if not Rank.query.filter_by(name=name).first():
                db.session.add(Rank(name=name, sort_order=i, note=note))

        db.session.commit()
        click.echo("マスタ（ステータス・確度ランク）の初期値を投入しました。")
