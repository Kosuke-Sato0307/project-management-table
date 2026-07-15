"""トップページ（ログイン後のダッシュボード）と部門選択。"""
from urllib.parse import urlparse

from flask import (Blueprint, render_template, request, redirect, url_for,
                   session, flash)
from flask_login import login_required, current_user

from ..decorators import password_change_guard, SESSION_DEPARTMENT_KEY
from ..models import Project, User
from .. import fiscal

main_bp = Blueprint("main", __name__)


def _is_safe_next(target):
    """オープンリダイレクト対策: 同一サイト内の相対パスのみ許可する。"""
    if not target:
        return False
    parsed = urlparse(target)
    return not parsed.scheme and not parsed.netloc and target.startswith("/")


@main_bp.route("/select-department")
@login_required
@password_change_guard
def select_department():
    """ログイン後にアクセスする部門を選ぶ画面。?dept=<id> 指定で選択を確定する。"""
    viewable = current_user.viewable_departments()
    next_url = request.args.get("next")
    dept_id = request.args.get("dept", type=int)

    if dept_id is not None:
        if not current_user.can_view_department(dept_id):
            flash("その部門にはアクセスできません。", "danger")
            return redirect(url_for("main.select_department", next=next_url))
        session[SESSION_DEPARTMENT_KEY] = dept_id
        if _is_safe_next(next_url):
            return redirect(next_url)
        return redirect(url_for("projects.list_projects"))

    current_id = session.get(SESSION_DEPARTMENT_KEY)
    return render_template("main/select_department.html", viewable=viewable,
                           current_id=current_id, next_url=next_url if _is_safe_next(next_url) else None)


@main_bp.route("/")
@login_required
@password_change_guard
def index():
    # ダッシュボードの簡易サマリ（システム管理者のみ集計・表示）
    project_count = user_count = None
    if current_user.is_sysadmin:
        project_count = Project.query.count()
        user_count = User.query.filter_by(is_active_flag=True).count()
    return render_template("main/index.html",
                           project_count=project_count,
                           user_count=user_count,
                           period_label=fiscal.period_label(fiscal.default_fiscal_period()))
