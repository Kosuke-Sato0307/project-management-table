"""共通デコレータ・部門スコープの解決ヘルパー。"""
from functools import wraps

from flask import abort, redirect, url_for, flash, request, session
from flask_login import current_user

from .extensions import db
from .models import Department
from . import fiscal


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


SESSION_DEPARTMENT_KEY = "current_department_id"


def resolve_department(require_edit: bool = False):
    """対象部門を決定して返す（ログイン後に選んだ部門をセッションで保持する方式）。

    - `?dept=<id>` が明示された場合はそれを採用し、以降のセッション既定部門にする。
    - 未指定なら、セッションに保持した部門（まだ閲覧可能なら）を使う。
    - セッションも無い場合、閲覧可能な部門が1つだけなら自動選択、
      複数あれば部門選択画面へ誘導する（要件: プルダウン廃止・ログイン後に部門を選ぶ）。
    - 閲覧権が無い部門を指定した場合は 403、無効/存在しない部門は 404。
    - require_edit=True の場合、部門単位の編集権が無ければ 403。
    戻り値: (department, viewable_departments)
    閲覧可能な部門が1つも無い場合は (None, []) を返す。
    """
    viewable = current_user.viewable_departments()
    if not viewable:
        return None, []
    viewable_ids = {d.id for d in viewable}

    dept_id = request.args.get("dept", type=int)
    if dept_id is not None:
        if not current_user.can_view_department(dept_id):
            abort(403)
        department = db.session.get(Department, dept_id)
        if department is None or not department.is_active:
            abort(404)
        session[SESSION_DEPARTMENT_KEY] = department.id
    else:
        sess_id = session.get(SESSION_DEPARTMENT_KEY)
        if sess_id in viewable_ids:
            department = db.session.get(Department, sess_id)
        elif len(viewable) == 1:
            department = viewable[0]
            session[SESSION_DEPARTMENT_KEY] = department.id
        else:
            # 部門が未選択（複数候補）→ 選択画面へ
            abort(redirect(url_for("main.select_department", next=request.full_path)))

    if require_edit and not current_user.can_edit_department(department.id):
        abort(403)
    return department, viewable


def resolve_period() -> int:
    """リクエストの ?period=<n> から対象の期を決定して返す。

    選択可能な期（fiscal.selectable_periods）に含まれる値のみ採用し、
    未指定・不正値のときは既定期（fiscal.default_fiscal_period）を返す。
    """
    requested = request.args.get("period", type=int)
    if requested is not None and requested in fiscal.selectable_periods():
        return requested
    return fiscal.default_fiscal_period()
