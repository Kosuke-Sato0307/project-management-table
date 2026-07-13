"""データベースのモデル定義（テーブル構造）。

拡張性方針:
  - 選択肢（案件ステータス・確度ランク）は「マスタテーブル」に切り出し、
    値の増減はコード変更なし（マスタ管理画面/シード）で行えるようにする。
  - 項目（カラム）の追加は Alembic マイグレーションで安全に行う。
"""
from datetime import datetime, timezone

import bcrypt
from flask_login import UserMixin

from .extensions import db


def _now() -> datetime:
    """UTCの現在時刻。保存はUTC、表示時にローカルへ変換する。"""
    return datetime.now(timezone.utc)


class User(UserMixin, db.Model):
    """ログインユーザー。管理者が事前登録する。"""
    __tablename__ = "users"

    # ログインID（例: yamada）。主キー。
    user_id = db.Column(db.String(64), primary_key=True)
    # 氏名（表示用）
    name = db.Column(db.String(128), nullable=False)
    # bcrypt でハッシュ化したパスワード
    password_hash = db.Column(db.String(255), nullable=False)
    # 権限: "admin"（管理者） / "user"（一般）
    role = db.Column(db.String(16), nullable=False, default="user")
    # 有効/無効（退職者などは無効化してログイン不可にする）
    is_active_flag = db.Column(db.Boolean, nullable=False, default=True)
    # 初回ログイン時にパスワード変更を強制するフラグ
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    # ---- パスワード関連ヘルパー ----
    def set_password(self, raw_password: str) -> None:
        self.password_hash = bcrypt.hashpw(
            raw_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, raw_password: str) -> bool:
        try:
            return bcrypt.checkpw(
                raw_password.encode("utf-8"), self.password_hash.encode("utf-8")
            )
        except (ValueError, AttributeError):
            return False

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    # ---- Flask-Login が要求するインターフェース ----
    def get_id(self) -> str:
        return self.user_id

    @property
    def is_active(self) -> bool:  # Flask-Login はこの名前を参照する
        return bool(self.is_active_flag)


class Status(db.Model):
    """案件ステータスのマスタ（進行中/受注/失注/完了 …）。"""
    __tablename__ = "statuses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    # 表示順（小さいほど先頭）
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    projects = db.relationship("Project", back_populates="status")


class Rank(db.Model):
    """確度ランクのマスタ（A/B/C … ）。"""
    __tablename__ = "ranks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(16), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    # 任意: ランクの意味メモ（例: "A=受注確実 80%以上"）
    note = db.Column(db.String(128), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    projects = db.relationship("Project", back_populates="rank")


class Department(db.Model):
    """部署のマスタ（第1営業部/大阪支店 …）。案件では名称を文字列で保持する。"""
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Project(db.Model):
    """案件。案件番号を主キーとする（手入力・重複はDBの一意制約で担保）。"""
    __tablename__ = "projects"

    project_no = db.Column(db.String(64), primary_key=True)          # 案件番号
    project_name = db.Column(db.String(255), nullable=False)         # 案件名
    customer_name = db.Column(db.String(255), nullable=True)         # 顧客名/取引先
    status_id = db.Column(db.Integer, db.ForeignKey("statuses.id"), nullable=True)  # 案件ステータス
    rank_id = db.Column(db.Integer, db.ForeignKey("ranks.id"), nullable=True)       # 確度
    estimate_no = db.Column(db.String(64), nullable=True)           # 見積番号
    amount_excl_tax = db.Column(db.Integer, nullable=True)          # 金額(税抜) 円
    completion_month = db.Column(db.String(7), nullable=True)       # 完成月 YYYY-MM
    order_date = db.Column(db.Date, nullable=True)                  # 受注日
    maintenance_start = db.Column(db.Date, nullable=True)           # 保守開始日
    maintenance_end = db.Column(db.Date, nullable=True)             # 保守終了日
    sales_rep = db.Column(db.String(128), nullable=True)           # 営業担当者
    department = db.Column(db.String(128), nullable=True)          # 部署
    notes = db.Column(db.Text, nullable=True)                      # 備考メモ

    # システム項目（自動記録）
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    created_by = db.Column(db.String(128), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    updated_by = db.Column(db.String(128), nullable=True)

    status = db.relationship("Status", back_populates="projects")
    rank = db.relationship("Rank", back_populates="projects")
