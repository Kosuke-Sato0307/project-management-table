"""共通デコレータ・部門スコープの解決ヘルパー。"""
from functools import wraps

from flask import abort, redirect, url_for, flash, request
from flask_login import current_user

from .extensions import db
from .models import Department


def admin_required(view):
    """システム管理者 or 管理者のみアクセス可能にするデコレータ。"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def sysadmin_required(view):
    """システム管理者のみアクセス可能にするデコレータ（ユーザー/システム管理）。"""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))
        if not current_user.is_sysadmin:
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


def resolve_department(require_edit: bool = False):
    """リクエストの ?dept=<id> から対象部門を決定して返す。

    - 指定が無ければ、閲覧可能な部門の先頭（既定部門）を使う。
    - 閲覧権が無い部門を指定した場合は 403。
    - require_edit=True の場合、部門単位の編集権が無ければ 403。
    戻り値: (department, viewable_departments)
    閲覧可能な部門が1つも無い場合は (None, []) を返す。
    """
    viewable = current_user.viewable_departments()
    if not viewable:
        return None, []

    dept_id = request.args.get("dept", type=int)
    if dept_id is None:
        department = viewable[0]
    else:
        if not current_user.can_view_department(dept_id):
            abort(403)
        department = db.session.get(Department, dept_id)
        if department is None or not department.is_active:
            abort(404)

    if require_edit and not current_user.can_edit_department(department.id):
        abort(403)
    return department, viewable
