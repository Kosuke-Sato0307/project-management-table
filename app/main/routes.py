"""トップページ（ログイン後のダッシュボード）。

フェーズ2以降で案件一覧・検索などを実装していく。まずは動作確認用の入口。
"""
from flask import Blueprint, render_template
from flask_login import login_required

from ..decorators import password_change_guard
from ..models import Project, User

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@login_required
@password_change_guard
def index():
    # ダッシュボードの簡易サマリ
    project_count = Project.query.count()
    user_count = User.query.filter_by(is_active_flag=True).count()
    return render_template("main/index.html",
                           project_count=project_count,
                           user_count=user_count)
