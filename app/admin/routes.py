"""管理者用: ユーザー管理。

ユーザーの一覧・新規登録（初期パスワード発行）・パスワードリセット・
有効/無効の切替・権限変更を行う。管理者のみアクセス可能。
"""
import secrets
import string

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash)
from flask_login import current_user

from ..extensions import db
from ..models import User, Status, Rank
from ..decorators import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _generate_temp_password(length: int = 10) -> str:
    """初期パスワードの自動生成（英大小＋数字、紛らわしい文字は除外）。"""
    alphabet = "".join(c for c in (string.ascii_letters + string.digits)
                       if c not in "O0l1I")
    return "".join(secrets.choice(alphabet) for _ in range(length))


@admin_bp.route("/users")
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.asc()).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/new", methods=["GET", "POST"])
@admin_required
def new_user():
    if request.method == "POST":
        user_id = (request.form.get("user_id") or "").strip()
        name = (request.form.get("name") or "").strip()
        role = request.form.get("role") or "user"

        if not user_id or not name:
            flash("ログインIDと氏名は必須です。", "danger")
            return render_template("admin/user_form.html")
        if role not in ("user", "admin"):
            role = "user"
        if db.session.get(User, user_id):
            flash(f"ログインID '{user_id}' は既に使われています。", "danger")
            return render_template("admin/user_form.html")

        temp_password = _generate_temp_password()
        user = User(user_id=user_id, name=name, role=role,
                    is_active_flag=True, must_change_password=True)
        user.set_password(temp_password)
        db.session.add(user)
        db.session.commit()

        # 初期パスワードは一度だけ画面表示（ハッシュ保存のため後から確認不可）
        flash(f"ユーザー '{name}'（{user_id}）を登録しました。"
              f"初期パスワードは「{temp_password}」です。本人に伝えてください"
              f"（初回ログイン時に変更が必要です）。", "success")
        return redirect(url_for("admin.users"))

    return render_template("admin/user_form.html")


@admin_bp.route("/users/<user_id>/reset-password", methods=["POST"])
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("対象ユーザーが見つかりません。", "danger")
        return redirect(url_for("admin.users"))

    temp_password = _generate_temp_password()
    user.set_password(temp_password)
    user.must_change_password = True
    db.session.commit()
    flash(f"'{user.name}' のパスワードをリセットしました。"
          f"新しい初期パスワードは「{temp_password}」です。", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<user_id>/toggle-active", methods=["POST"])
@admin_required
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


@admin_bp.route("/users/<user_id>/role", methods=["POST"])
@admin_required
def change_role(user_id):
    user = db.session.get(User, user_id)
    if user is None:
        flash("対象ユーザーが見つかりません。", "danger")
        return redirect(url_for("admin.users"))
    new_role = request.form.get("role")
    if new_role not in ("user", "admin"):
        flash("不正な権限です。", "danger")
        return redirect(url_for("admin.users"))
    # 最後の管理者を一般ユーザーに降格させない安全策
    if user.is_admin and new_role == "user":
        admin_count = User.query.filter_by(role="admin", is_active_flag=True).count()
        if admin_count <= 1:
            flash("管理者が1人だけのため、権限を変更できません。", "danger")
            return redirect(url_for("admin.users"))

    user.role = new_role
    db.session.commit()
    flash(f"'{user.name}' の権限を変更しました。", "info")
    return redirect(url_for("admin.users"))


# ============ マスタ管理: 案件ステータス ============
@admin_bp.route("/statuses")
@admin_required
def statuses():
    items = Status.query.order_by(Status.sort_order, Status.id).all()
    return render_template("admin/statuses.html", items=items)


@admin_bp.route("/statuses/new", methods=["POST"])
@admin_required
def new_status():
    name = (request.form.get("name") or "").strip()
    sort_order = request.form.get("sort_order", type=int) or 0
    if not name:
        flash("名称を入力してください。", "danger")
    elif Status.query.filter_by(name=name).first():
        flash(f"'{name}' は既に存在します。", "danger")
    else:
        db.session.add(Status(name=name, sort_order=sort_order))
        db.session.commit()
        flash(f"ステータス '{name}' を追加しました。", "success")
    return redirect(url_for("admin.statuses"))


@admin_bp.route("/statuses/<int:item_id>/edit", methods=["POST"])
@admin_required
def edit_status(item_id):
    item = db.session.get(Status, item_id)
    if item is None:
        flash("対象が見つかりません。", "danger")
        return redirect(url_for("admin.statuses"))
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("名称を入力してください。", "danger")
        return redirect(url_for("admin.statuses"))
    dup = Status.query.filter_by(name=name).first()
    if dup and dup.id != item.id:
        flash(f"'{name}' は既に存在します。", "danger")
        return redirect(url_for("admin.statuses"))
    item.name = name
    item.sort_order = request.form.get("sort_order", type=int) or 0
    db.session.commit()
    flash("ステータスを更新しました。", "success")
    return redirect(url_for("admin.statuses"))


@admin_bp.route("/statuses/<int:item_id>/toggle", methods=["POST"])
@admin_required
def toggle_status(item_id):
    item = db.session.get(Status, item_id)
    if item:
        item.is_active = not item.is_active
        db.session.commit()
        flash("表示/非表示を切り替えました。", "info")
    return redirect(url_for("admin.statuses"))


# ============ マスタ管理: 確度ランク ============
@admin_bp.route("/ranks")
@admin_required
def ranks():
    items = Rank.query.order_by(Rank.sort_order, Rank.id).all()
    return render_template("admin/ranks.html", items=items)


@admin_bp.route("/ranks/new", methods=["POST"])
@admin_required
def new_rank():
    name = (request.form.get("name") or "").strip()
    note = (request.form.get("note") or "").strip() or None
    sort_order = request.form.get("sort_order", type=int) or 0
    if not name:
        flash("名称を入力してください。", "danger")
    elif Rank.query.filter_by(name=name).first():
        flash(f"'{name}' は既に存在します。", "danger")
    else:
        db.session.add(Rank(name=name, note=note, sort_order=sort_order))
        db.session.commit()
        flash(f"確度ランク '{name}' を追加しました。", "success")
    return redirect(url_for("admin.ranks"))


@admin_bp.route("/ranks/<int:item_id>/edit", methods=["POST"])
@admin_required
def edit_rank(item_id):
    item = db.session.get(Rank, item_id)
    if item is None:
        flash("対象が見つかりません。", "danger")
        return redirect(url_for("admin.ranks"))
    name = (request.form.get("name") or "").strip()
    if not name:
        flash("名称を入力してください。", "danger")
        return redirect(url_for("admin.ranks"))
    dup = Rank.query.filter_by(name=name).first()
    if dup and dup.id != item.id:
        flash(f"'{name}' は既に存在します。", "danger")
        return redirect(url_for("admin.ranks"))
    item.name = name
    item.note = (request.form.get("note") or "").strip() or None
    item.sort_order = request.form.get("sort_order", type=int) or 0
    db.session.commit()
    flash("確度ランクを更新しました。", "success")
    return redirect(url_for("admin.ranks"))


@admin_bp.route("/ranks/<int:item_id>/toggle", methods=["POST"])
@admin_required
def toggle_rank(item_id):
    item = db.session.get(Rank, item_id)
    if item:
        item.is_active = not item.is_active
        db.session.commit()
        flash("表示/非表示を切り替えました。", "info")
    return redirect(url_for("admin.ranks"))
