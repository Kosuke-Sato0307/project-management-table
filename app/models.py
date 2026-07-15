"""データベースのモデル定義（テーブル構造）。

59期リニューアルの設計方針:
  - 案件(Project)は「案件番号」ではなく整数IDを主キーとする（案件番号未発行の案件も
    集計できるように）。案件は必ず「部門」と「計上月(YYYY-MM)」を持つ。
  - 権限は3段階（システム管理者 / 管理者=部門長 / 一般）。ユーザーと部門は多対多。
  - 選択肢（確度・区分・カテゴリー）は「マスタテーブル」に切り出し、コード変更なしで
    増減できるようにする。カテゴリーは部門ごとに異なりうるため部門に紐づける。
"""
from datetime import datetime, timezone

import bcrypt
from flask_login import UserMixin

from .extensions import db


def _now() -> datetime:
    """UTCの現在時刻。保存はUTC、表示時にローカルへ変換する。"""
    return datetime.now(timezone.utc)


# ---- 権限（ロール）定数 ----
ROLE_SYSADMIN = "sysadmin"   # システム管理者：全権（ユーザー/システム管理）
ROLE_ADMIN = "admin"         # 管理者：部門長クラス。全部門を閲覧、自部門のみ編集
ROLE_USER = "user"           # 一般：自部門を閲覧、自分が担当の案件のみ編集

ROLE_LABELS = {
    ROLE_SYSADMIN: "システム管理者",
    ROLE_ADMIN: "管理者",
    ROLE_USER: "一般ユーザー",
}
VALID_ROLES = (ROLE_SYSADMIN, ROLE_ADMIN, ROLE_USER)


# ユーザーと部門の多対多（1ユーザーに複数部門を割り当て可能）
# こちらは「所属部門」。担当者候補（department.members）を駆動する。
user_departments = db.Table(
    "user_departments",
    db.Column("user_id", db.String(64), db.ForeignKey("users.user_id"), primary_key=True),
    db.Column("department_id", db.Integer, db.ForeignKey("departments.id"), primary_key=True),
)

# 部門長（管理者）の「閲覧・編集可能な部門」（所属とは別枠）。
# ここに入れても department.members には含めない＝担当者候補に名前が出ない。
user_manageable_departments = db.Table(
    "user_manageable_departments",
    db.Column("user_id", db.String(64), db.ForeignKey("users.user_id"), primary_key=True),
    db.Column("department_id", db.Integer, db.ForeignKey("departments.id"), primary_key=True),
)


class User(UserMixin, db.Model):
    """ログインユーザー。管理者が事前登録する。"""
    __tablename__ = "users"

    # ログインID（例: yamada）。主キー。
    user_id = db.Column(db.String(64), primary_key=True)
    # 氏名（表示用）
    name = db.Column(db.String(128), nullable=False)
    # bcrypt でハッシュ化したパスワード
    password_hash = db.Column(db.String(255), nullable=False)
    # 権限: sysadmin / admin / user
    role = db.Column(db.String(16), nullable=False, default=ROLE_USER)
    # 有効/無効（退職者などは無効化してログイン不可にする）
    is_active_flag = db.Column(db.Boolean, nullable=False, default=True)
    # 初回ログイン時にパスワード変更を強制するフラグ
    must_change_password = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=_now)

    # 所属部門（多対多）。担当者候補（department.members）を駆動する。
    departments = db.relationship(
        "Department", secondary=user_departments,
        order_by="Department.sort_order",
        backref=db.backref("members", order_by="User.user_id"),
    )

    # 閲覧・編集可能な部門（部門長のみ・所属とは別枠）。担当者候補には含めない。
    manageable_departments = db.relationship(
        "Department", secondary=user_manageable_departments,
        order_by="Department.sort_order",
    )

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

    # ---- 権限判定 ----
    @property
    def is_sysadmin(self) -> bool:
        return self.role == ROLE_SYSADMIN

    @property
    def is_manager(self) -> bool:
        """管理者（部門長）。"""
        return self.role == ROLE_ADMIN

    @property
    def is_admin(self) -> bool:
        """システム管理者 or 管理者（＝一般ユーザーより上位）。"""
        return self.role in (ROLE_SYSADMIN, ROLE_ADMIN)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def department_ids(self) -> set[int]:
        """所属部門ID（担当者候補に名前が出る部門）。"""
        return {d.id for d in self.departments}

    @property
    def manageable_department_ids(self) -> set[int]:
        """閲覧・編集可能部門ID（部門長のみ・所属とは別枠）。"""
        return {d.id for d in self.manageable_departments}

    @property
    def admin_scope_ids(self) -> set[int]:
        """管理者が閲覧・編集できる部門ID（所属 ∪ 閲覧編集部門）。"""
        return self.department_ids | self.manageable_department_ids

    def viewable_departments(self):
        """閲覧できる部門の一覧（sort順）。

        システム管理者は全部門、管理者は「所属 ∪ 閲覧編集部門」、一般は自部門のみ。
        """
        if self.role == ROLE_SYSADMIN:
            return Department.query.filter_by(is_active=True) \
                .order_by(Department.sort_order).all()
        if self.role == ROLE_ADMIN:
            depts = {d.id: d for d in self.departments if d.is_active}
            depts.update({d.id: d for d in self.manageable_departments if d.is_active})
            return sorted(depts.values(), key=lambda d: d.sort_order)
        return sorted(self.departments, key=lambda d: d.sort_order)

    def editable_departments(self):
        """『部門単位で』編集できる部門の一覧（販管費入力・部門の案件編集の判定に使う）。

        システム管理者は全部門、管理者は「所属 ∪ 閲覧編集部門」、一般は自部門のみ。
        （一般は部門単位の編集権は無いが、自部門として編集画面に入る起点に使う。）
        """
        if self.role == ROLE_SYSADMIN:
            return Department.query.filter_by(is_active=True) \
                .order_by(Department.sort_order).all()
        if self.role == ROLE_ADMIN:
            depts = {d.id: d for d in self.departments if d.is_active}
            depts.update({d.id: d for d in self.manageable_departments if d.is_active})
            return sorted(depts.values(), key=lambda d: d.sort_order)
        return sorted(self.departments, key=lambda d: d.sort_order)

    def can_view_department(self, department_id: int) -> bool:
        if self.role == ROLE_SYSADMIN:
            return True
        if self.role == ROLE_ADMIN:
            return department_id in self.admin_scope_ids
        return department_id in self.department_ids

    def can_edit_department(self, department_id: int) -> bool:
        """部門の販管費など『部門単位』の編集可否。"""
        if self.role == ROLE_SYSADMIN:
            return True
        if self.role == ROLE_ADMIN:
            return department_id in self.admin_scope_ids
        return False

    def can_view_project(self, project) -> bool:
        return self.can_view_department(project.department_id)

    def can_edit_project(self, project) -> bool:
        """案件の編集/削除可否。

        - システム管理者: すべて
        - 管理者: 自分の紐づく部門の案件
        - 一般: 自分が担当として登録されている案件のみ
        """
        if self.role == ROLE_SYSADMIN:
            return True
        if self.role == ROLE_ADMIN:
            return project.department_id in self.admin_scope_ids
        return project.assignee_user_id == self.user_id

    # ---- Flask-Login が要求するインターフェース ----
    def get_id(self) -> str:
        return self.user_id

    @property
    def is_active(self) -> bool:  # Flask-Login はこの名前を参照する
        return bool(self.is_active_flag)


class Department(db.Model):
    """部門のマスタ（第2営業部 など）。案件・ユーザー・販管費が紐づく。"""
    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


class Rank(db.Model):
    """確度ランクのマスタ（○ / A / B / … / ×）。'○' を実績（受注確定）とみなす。"""
    __tablename__ = "ranks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(16), nullable=False, unique=True)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    # 任意: ランクの意味メモ（例: "○=受注確定"）
    note = db.Column(db.String(128), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    projects = db.relationship("Project", back_populates="rank")

    # 実績（受注確定）とみなす確度の名称
    ACTUAL_NAME = "○"

    @property
    def is_actual(self) -> bool:
        return self.name == self.ACTUAL_NAME


class Kubun(db.Model):
    """区分マスタ（期初計画 / 新規）。

    注: 計画/実績の判定は Project.plan_type へ移行したため、is_plan は集計に未使用。
    区分は案件の自由な分類項目として存続する。
    """
    __tablename__ = "kubun"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), nullable=False, unique=True)
    # 旧: 期初計画かどうかの判定に使用。現在は集計未使用（plan_type へ移行）。
    is_plan = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    projects = db.relationship("Project", back_populates="kubun")

    # 期初計画の区分名
    PLAN_NAME = "期初計画"


class Category(db.Model):
    """カテゴリーマスタ（Ri=Ribbon Communications関連 など）。部門ごとに定義できる。"""
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    code = db.Column(db.String(16), nullable=False)      # Ri / Or / Au / Kd / NM / Ot
    name = db.Column(db.String(128), nullable=False)     # 名称（Ribbon Communications関連 等）
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    department = db.relationship("Department")
    projects = db.relationship("Project", back_populates="category")

    @property
    def display_name(self) -> str:
        """'Ri（Ribbon Communications関連）' 形式。"""
        return f"{self.code}（{self.name}）"


class ProductCategory(db.Model):
    """商品カテゴリのマスタ（GW-保守 など）。部門ごとに定義でき、システム管理者と
    部門管理者（部門長）がカスタマイズできる。数字まとめで商品カテゴリ別の集計に使う。"""
    __tablename__ = "product_categories"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    name = db.Column(db.String(64), nullable=False)      # GW-保守 / 音声-保守 等
    sort_order = db.Column(db.Integer, nullable=False, default=0)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    department = db.relationship("Department")
    projects = db.relationship("Project", back_populates="product_category")


class Project(db.Model):
    """案件。整数IDを主キーとし、部門・計上月ごとに集計する。

    列の並び（画面表示順）は依頼どおり:
      担当者 / 区分 / カテゴリー / 案件名 / 確度 / 売上 / 仕入 / 売上総利益 /
      見込み工数 / 対応工数 / 備考
    売上総利益は保存せず、売上−仕入で自動計算する。

    plan_type で3つのデータセットを区別する（計画判定は Kubun.is_plan から plan_type へ移行）:
      - initial   … 期初計画（計画値）
      - midterm   … 中期計画（独立した計画値）
      - management … 案件管理（実績見込み。確度○の行を実績値として算出）
    """
    __tablename__ = "projects"

    # データセット種別
    PLAN_INITIAL = "initial"
    PLAN_MIDTERM = "midterm"
    PLAN_MANAGEMENT = "management"
    PLAN_TYPES = (PLAN_INITIAL, PLAN_MIDTERM, PLAN_MANAGEMENT)
    PLAN_TYPE_LABELS = {
        PLAN_INITIAL: "期初計画",
        PLAN_MIDTERM: "中期計画",
        PLAN_MANAGEMENT: "案件管理",
    }

    id = db.Column(db.Integer, primary_key=True)

    # 集計軸
    fiscal_period = db.Column(db.Integer, nullable=False, default=59)   # 期（59 など）
    # データセット種別（期初計画 / 中期計画 / 案件管理）
    plan_type = db.Column(db.String(16), nullable=False,
                          default=PLAN_MANAGEMENT, index=True)
    accounting_month = db.Column(db.String(7), nullable=False)         # 計上月 YYYY-MM
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)

    # 表示順の項目
    assignee_user_id = db.Column(db.String(64), db.ForeignKey("users.user_id"), nullable=True)  # 担当者
    # 担当者名のスナップショット（担当ユーザー削除後も氏名を残すため保存する）
    assignee_name = db.Column(db.String(128), nullable=True)
    kubun_id = db.Column(db.Integer, db.ForeignKey("kubun.id"), nullable=True)                   # 区分
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=True)           # カテゴリー
    project_name = db.Column(db.String(255), nullable=False)                                     # 案件名
    client_name = db.Column(db.String(255), nullable=True)                                       # 取引先
    end_user_name = db.Column(db.String(255), nullable=True)                                     # エンドユーザ
    product_category_id = db.Column(db.Integer, db.ForeignKey("product_categories.id"),
                                    nullable=True)                                               # 商品カテゴリ
    rank_id = db.Column(db.Integer, db.ForeignKey("ranks.id"), nullable=True)                    # 確度
    sales = db.Column(db.Integer, nullable=True)                                                 # 売上 円
    cost = db.Column(db.Integer, nullable=True)                                                  # 仕入 円
    # 売上総利益 = 売上 - 仕入（プロパティで算出、DBには保存しない）
    estimated_hours = db.Column(db.Float, nullable=True)                                         # 見込み工数
    actual_hours = db.Column(db.Float, nullable=True)                                            # 対応工数
    notes = db.Column(db.Text, nullable=True)                                                    # 備考

    # システム項目（自動記録）
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    created_by = db.Column(db.String(128), nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    updated_by = db.Column(db.String(128), nullable=True)

    department = db.relationship("Department")
    assignee = db.relationship("User")
    kubun = db.relationship("Kubun", back_populates="projects")
    category = db.relationship("Category", back_populates="projects")
    product_category = db.relationship("ProductCategory", back_populates="projects")
    rank = db.relationship("Rank", back_populates="projects")

    @property
    def assignee_display(self) -> str:
        """担当者の表示名。存命ユーザーは氏名、削除済みはスナップショット名。"""
        if self.assignee is not None:
            return self.assignee.name
        return self.assignee_name or ""

    @property
    def gross_profit(self) -> int:
        """売上総利益 = 売上 − 仕入（未入力は0扱い）。"""
        return (self.sales or 0) - (self.cost or 0)

    @property
    def is_actual(self) -> bool:
        """実績（受注確定 = 確度○）かどうか。"""
        return self.rank is not None and self.rank.is_actual

    @property
    def is_initial_plan(self) -> bool:
        """期初計画のデータか。"""
        return self.plan_type == self.PLAN_INITIAL

    @property
    def is_midterm_plan(self) -> bool:
        """中期計画のデータか。"""
        return self.plan_type == self.PLAN_MIDTERM

    @property
    def is_management(self) -> bool:
        """案件管理（実績見込み）のデータか。"""
        return self.plan_type == self.PLAN_MANAGEMENT


class Sga(db.Model):
    """販管費（月次・部門別に手入力）。四半期/半期/通期は月の合計で自動算出する。"""
    __tablename__ = "sga"

    id = db.Column(db.Integer, primary_key=True)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=False)
    fiscal_period = db.Column(db.Integer, nullable=False, default=59)
    month = db.Column(db.String(7), nullable=False)   # YYYY-MM
    amount = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        db.UniqueConstraint("department_id", "fiscal_period", "month",
                            name="uq_sga_dept_period_month"),
    )

    department = db.relationship("Department")
