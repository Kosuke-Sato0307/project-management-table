"""認証（ログイン・ログアウト・パスワード変更）。"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash)
from flask_login import login_user, logout_user, login_required, current_user

from ..extensions import db
from ..models import User

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    # 既にログイン済みならトップへ
    if current_user.is_authenticated:
        return redirect(url_for("main.index"))

    if request.method == "POST":
        user_id = (request.form.get("user_id") or "").strip()
        password = request.form.get("password") or ""
        user = db.session.get(User, user_id)

        if user is None or not user.check_password(password):
            flash("ログインIDまたはパスワードが違います。", "danger")
            return render_template("auth/login.html"), 401
        if not user.is_active:
            flash("このアカウントは無効化されています。管理者にご連絡ください。", "danger")
            return render_template("auth/login.html"), 403

        login_user(user)
        # 初回はパスワード変更へ
        if user.must_change_password:
            flash("初回ログインです。パスワードを変更してください。", "warning")
            return redirect(url_for("auth.change_password"))
        return redirect(url_for("main.index"))

    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("ログアウトしました。", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password") or ""
        new_pw = request.form.get("new_password") or ""
        new_pw2 = request.form.get("new_password_confirm") or ""

        # 初回変更時は現在のパスワード確認を省略しない（本人確認のため）
        if not current_user.check_password(current_pw):
            flash("現在のパスワードが違います。", "danger")
            return render_template("auth/change_password.html")
        if len(new_pw) < 8:
            flash("新しいパスワードは8文字以上にしてください。", "danger")
            return render_template("auth/change_password.html")
        if new_pw != new_pw2:
            flash("新しいパスワード（確認）が一致しません。", "danger")
            return render_template("auth/change_password.html")
        if new_pw == current_pw:
            flash("現在のパスワードと異なるものを設定してください。", "danger")
            return render_template("auth/change_password.html")

        current_user.set_password(new_pw)
        current_user.must_change_password = False
        db.session.commit()
        flash("パスワードを変更しました。", "success")
        return redirect(url_for("main.index"))

    return render_template("auth/change_password.html")
