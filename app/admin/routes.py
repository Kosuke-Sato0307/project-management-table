"""システム管理者用: ユーザー管理・マスタ管理。

ユーザーの一覧・新規登録（初期パスワード発行）・パスワードリセット・
有効/無効の切替・権限変更・所属部門の割り当てを行う。
カテゴリーマスタ（部門別）の追加/編集/無効化もここで扱う。
いずれもシステム管理者のみアクセス可能。
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort)
from flask_login import current_user

from ..extensions import db
from ..models import (User, Department, Category, ProductCategory, Project,
                      VALID_ROLES, ROLE_USER, ROLE_ADMIN)
from ..decorators import sysadmin_required, admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# 初期パスワードは案内簡略化のため固定値とする（初回ログイン時に変更が必要）。
INITIAL_PASSWORD = "P@ssw0rd"


def _selected_departments(field="department_ids"):
    """フォームから選択された部門ID群を有効な Department リストにして返す。"""
    ids = request.form.getlist(field, type=int)
    if not ids:
        return []
    return Department.query.filter(
        Department.id.in_(ids), Department.is_active.is_(True)
    ).all()


@admin_bp.route("/users")
@sysadmin_required
def users():
    all_users = User.query.order_by(User.created_at.asc()).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@sysadmin_required
def new_user():
    departments = Department.query.filter_by(is_active=True) \
        .order_by(Department.sort_order).all()
    if request.method == "POST":
        user_id = (request.form.get("user_id") or "").strip()
        name = (request.form.get("name") or "").strip()
        role = request.form.get("role") or ROLE_USER

        if not user_id or not name:
            flash("ログインIDと氏名は必須です。", "danger")
            return render_template("admin/user_form.html", departments=departments,
                                   form=request.form)
        if role not in VALID_ROLES:
            role = ROLE_USER
        if db.session.get(User, user_id):
            flash(f"ログインID '{user_id}' は既に使われています。", "danger")
            return render_template("admin/user_form.html", departments=departments,
                                   form=request.form)

        user = User(user_id=user_id, name=name, role=role,
                    is_active_flag=True, must_change_password=True)
        user.set_password(INITIAL_PASSWORD)
        user.departments = _selected_departments()
        # 閲覧・編集可能部門は部門長（管理者）のみ意味を持つ
        user.manageable_departments = (
            _selected_departments("manageable_department_ids")
            if role == ROLE_ADMIN else [])
        db.session.add(user)
        db.session.commit()

        flash(f"ユーザー '{name}'（{user_id}）を登録しました。"
              f"初期パスワードは「{INITIAL_PASSWORD}」です。本人に伝えてください"
              f"（初回ログイン時に変更が必要です）。", "success")
        return redirect(url_for("admin.users"))

    return render_template("admin/user_form.html", departments=departments, form={})


@admin_bp.route("/users/<user_id>/edit", methods=["GET", "POST"])
@sysadmin_required
def edit_user(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("対象ユーザーが見つかりません。", "danger")
        return redirect(url_for("admin.users"))
    departments = Department.query.filter_by(is_active=True) \
        .order_by(Department.sort_order).all()

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        role = request.form.get("role") or ROLE_USER
        if not name:
            flash("氏名は必須です。", "danger")
            return render_template("admin/user_edit.html", user=user,
                                   departments=departments)
        if role not in VALID_ROLES:
            role = ROLE_USER
        # 最後のシステム管理者を降格させない安全策
        if user.is_sysadmin and role != "sysadmin":
            others = User.query.filter_by(role="sysadmin", is_active_flag=True) \
                .filter(User.user_id != user.user_id).count()
            if others == 0:
                flash("システム管理者が1人だけのため、権限を変更できません。", "danger")
                return render_template("admin/user_edit.html", user=user,
                                       departments=departments)

        user.name = name
        user.role = role
        user.departments = _selected_departments()
        user.manageable_departments = (
            _selected_departments("manageable_department_ids")
            if role == ROLE_ADMIN else [])
        db.session.commit()
        flash(f"'{user.name}' の情報を更新しました。", "success")
        return redirect(url_for("admin.users"))

    return render_template("admin/user_edit.html", user=user,
                           departments=departments)


@admin_bp.route("/users/<user_id>/reset-password", methods=["POST"])
@sysadmin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("対象ユーザーが見つかりません。", "danger")
        return redirect(url_for("admin.users"))

    user.set_password(INITIAL_PASSWORD)
    user.must_change_password = True
    db.session.commit()
    flash(f"'{user.name}' のパスワードをリセットしました。"
          f"新しい初期パスワードは「{INITIAL_PASSWORD}」です。", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<user_id>/toggle-active", methods=["POST"])
@sysadmin_required
def toggle_active(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("対象ユーザーが見つかりません。", "danger")
        return redirect(url_for("admin.users"))
    if user.user_id == current_user.user_id:
        flash("自分自身は無効化できません。", "danger")
        return redirect(url_for("admin.users"))

    user.is_active_flag = not user.is_active_flag
    db.session.commit()
    state = "有効化" if user.is_active_flag else "無効化"
    flash(f"'{user.name}' を{state}しました。", "info")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<user_id>/delete", methods=["POST"])
@sysadmin_required
def delete_user(user_id):
    """ユーザーを削除する。担当していた案件は、担当者名だけを残して担当者リンクを外す。"""
    user = db.session.get(User, user_id)
    if user is None:
        flash("対象ユーザーが見つかりません。", "danger")
        return redirect(url_for("admin.users"))
    if user.user_id == current_user.user_id:
        flash("自分自身は削除できません。", "danger")
        return redirect(url_for("admin.users"))
    # 最後の有効なシステム管理者は削除しない安全策
    if user.is_sysadmin:
        others = User.query.filter_by(role="sysadmin", is_active_flag=True) \
            .filter(User.user_id != user.user_id).count()
        if others == 0:
            flash("システム管理者が1人だけのため、削除できません。", "danger")
            return redirect(url_for("admin.users"))

    # 担当していた案件は氏名を残して担当者リンクを外す（過去の案件管理・期初計画で名前を保持）
    assigned = Project.query.filter_by(assignee_user_id=user.user_id).all()
    for p in assigned:
        if not p.assignee_name:
            p.assignee_name = user.name
        p.assignee_user_id = None

    name = user.name
    user.departments = []
    user.manageable_departments = []
    db.session.delete(user)
    db.session.commit()
    flash(f"ユーザー '{name}'（{user_id}）を削除しました。"
          f"担当していた案件には担当者名を残しています。", "info")
    return redirect(url_for("admin.users"))


# ---------- カテゴリーマスタ（部門別） ----------
@admin_bp.route("/categories", methods=["GET", "POST"])
@sysadmin_required
def categories():
    departments = Department.query.filter_by(is_active=True) \
        .order_by(Department.sort_order).all()
    dept_id = request.values.get("dept", type=int)
    department = None
    if dept_id is not None:
        department = db.session.get(Department, dept_id)
    elif departments:
        department = departments[0]

    if request.method == "POST" and department is not None:
        code = (request.form.get("code") or "").strip()
        name = (request.form.get("name") or "").strip()
        if not code or not name:
            flash("コードと名称は必須です。", "danger")
        else:
            max_order = db.session.query(db.func.max(Category.sort_order)) \
                .filter_by(department_id=department.id).scalar() or 0
            db.session.add(Category(department_id=department.id, code=code,
                                    name=name, sort_order=max_order + 1))
            db.session.commit()
            flash(f"カテゴリー '{code}（{name}）' を追加しました。", "success")
        return redirect(url_for("admin.categories", dept=department.id))

    items = []
    if department is not None:
        items = Category.query.filter_by(department_id=department.id) \
            .order_by(Category.sort_order).all()
    return render_template("admin/categories.html", departments=departments,
                           department=department, categories=items)


@admin_bp.route("/categories/<int:category_id>/toggle-active", methods=["POST"])
@sysadmin_required
def toggle_category(category_id):
    cat = db.session.get(Category, category_id)
    if cat is None:
        flash("対象カテゴリーが見つかりません。", "danger")
        return redirect(url_for("admin.categories"))
    cat.is_active = not cat.is_active
    db.session.commit()
    state = "有効化" if cat.is_active else "無効化"
    flash(f"カテゴリー '{cat.code}' を{state}しました。", "info")
    return redirect(url_for("admin.categories", dept=cat.department_id))


# ---------- 商品カテゴリマスタ（部門別・システム管理者＋部門管理者） ----------
def _product_category_departments():
    """商品カテゴリを管理できる部門（sysadmin=全部門 / 管理者=編集可能部門）。"""
    return current_user.editable_departments()


@admin_bp.route("/product-categories", methods=["GET", "POST"])
@admin_required
def product_categories():
    departments = _product_category_departments()
    dept_id = request.values.get("dept", type=int)
    department = None
    if dept_id is not None:
        department = next((d for d in departments if d.id == dept_id), None)
        if department is None:
            abort(403)
    elif departments:
        department = departments[0]

    if request.method == "POST" and department is not None:
        if not current_user.can_edit_department(department.id):
            abort(403)
        name = (request.form.get("name") or "").strip()
        if not name:
            flash("名称は必須です。", "danger")
        else:
            max_order = db.session.query(db.func.max(ProductCategory.sort_order)) \
                .filter_by(department_id=department.id).scalar() or 0
            db.session.add(ProductCategory(department_id=department.id, name=name,
                                           sort_order=max_order + 1))
            db.session.commit()
            flash(f"商品カテゴリ '{name}' を追加しました。", "success")
        return redirect(url_for("admin.product_categories", dept=department.id))

    items = []
    if department is not None:
        items = ProductCategory.query.filter_by(department_id=department.id) \
            .order_by(ProductCategory.sort_order).all()
    return render_template("admin/product_categories.html", departments=departments,
                           department=department, product_categories=items)


@admin_bp.route("/product-categories/<int:pc_id>/toggle-active", methods=["POST"])
@admin_required
def toggle_product_category(pc_id):
    pc = db.session.get(ProductCategory, pc_id)
    if pc is None:
        flash("対象の商品カテゴリが見つかりません。", "danger")
        return redirect(url_for("admin.product_categories"))
    if not current_user.can_edit_department(pc.department_id):
        abort(403)
    pc.is_active = not pc.is_active
    db.session.commit()
    state = "有効化" if pc.is_active else "無効化"
    flash(f"商品カテゴリ '{pc.name}' を{state}しました。", "info")
    return redirect(url_for("admin.product_categories", dept=pc.department_id))
