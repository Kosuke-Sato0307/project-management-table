"""共通デコレータ。"""
from functools import wraps

from flask import abort, redirect, url_for, flash
from flask_login import current_user


def admin_required(view):
    """管理者のみアクセス可能にするデコレータ。"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def password_change_guard(view):
    """初回パスワード変更が未完了のユーザーを変更画面へ誘導する。"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user.is_authenticated and current_user.must_change_password:
            flash("初回ログインです。パスワードを変更してください。", "warning")
            return redirect(url_for("auth.change_password"))
        return view(*args, **kwargs)
    return wrapped
