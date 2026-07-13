"""管理者用: ユーザー管理。

ユーザーの一覧・新規登録（初期パスワード発行）・パスワードリセット・
有効/無効の切替・権限変更を行う。管理者のみアクセス可能。
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash)
from flask_login import current_user

from ..extensions import db
from ..models import User
from ..decorators import admin_required

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

# 初期パスワードは案内簡略化のため固定値とする（初回ログイン時に変更が必要）。
INITIAL_PASSWORD = "P@ssw0rd"


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

        user = User(user_id=user_id, name=name, role=role,
                    is_active_flag=True, must_change_password=True)
        user.set_password(INITIAL_PASSWORD)
        db.session.add(user)
        db.session.commit()

        flash(f"ユーザー '{name}'（{user_id}）を登録しました。"
              f"初期パスワードは「{INITIAL_PASSWORD}」です。本人に伝えてください"
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

    user.set_password(INITIAL_PASSWORD)
    user.must_change_password = True
    db.session.commit()
    flash(f"'{user.name}' のパスワードをリセットしました。"
          f"新しい初期パスワードは「{INITIAL_PASSWORD}」です。", "success")
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
