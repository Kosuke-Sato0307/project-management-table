"""トップページ（ログイン後のダッシュボード）。"""
from flask import Blueprint, render_template
from flask_login import login_required, current_user

from ..decorators import password_change_guard
from ..models import Project, User
from .. import fiscal

main_bp = Blueprint("main", __name__)


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
