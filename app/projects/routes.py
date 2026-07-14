"""案件（案件管理表）の一覧・登録・編集・削除。

部門スコープ:
  - 一覧/詳細は「閲覧可能な部門」に限定（?dept=<id>）。
  - 登録/編集/削除は can_edit_project に従う
    （システム管理者=全て / 管理者=自部門 / 一般=自担当のみ）。
案件は部門内で計上月ごとにまとめて表示する。
"""
from datetime import datetime

from urllib.parse import quote

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, make_response)
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Project, Rank, Kubun, Category, Department, User
from ..decorators import password_change_guard, resolve_department, resolve_period
from .. import exporters
from .. import fiscal

projects_bp = Blueprint("projects", __name__, url_prefix="/projects")


def _resolve_plan_type():
    """?type=initial|midterm|management を検証。既定は案件管理(management)。"""
    pt = request.values.get("type")
    if pt in Project.PLAN_TYPES:
        return pt
    return Project.PLAN_MANAGEMENT


def _existing_periods(department):
    """その部門の案件に存在する期の一覧（期セレクタの選択肢用）。"""
    rows = db.session.query(Project.fiscal_period).filter_by(
        department_id=department.id).distinct().all()
    return [r[0] for r in rows]


# ---------- 入力パース/検証のヘルパー ----------
def _clean(value):
    """空文字は None に、前後空白は除去。"""
    if value is None:
        return None
    value = value.strip()
    return value or None


def _parse_int(value, field_label, errors):
    value = _clean(value)
    if value is None:
        return None
    normalized = value.replace(",", "").replace("，", "").translate(
        str.maketrans("０１２３４５６７８９", "0123456789"))
    try:
        return int(normalized)
    except ValueError:
        errors.append(f"{field_label}は数字で入力してください。")
        return None


def _parse_float(value, field_label, errors):
    value = _clean(value)
    if value is None:
        return None
    normalized = value.replace(",", "").replace("，", "").translate(
        str.maketrans("０１２３４５６７８９．", "0123456789."))
    try:
        return float(normalized)
    except ValueError:
        errors.append(f"{field_label}は数字で入力してください。")
        return None


def _parse_month(value, field_label, errors):
    """計上月。yyyy/m または yyyy-mm を受理し、保存用に 'YYYY-MM' へ正規化。"""
    value = _clean(value)
    if value is None:
        errors.append(f"{field_label}は必須です。")
        return None
    normalized = value.replace("/", "-")
    try:
        dt = datetime.strptime(normalized, "%Y-%m")
        return dt.strftime("%Y-%m")
    except ValueError:
        errors.append(f"{field_label}は 2026/9 の形式で入力してください。")
        return None


def _parse_fk(value):
    value = _clean(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _masters(department):
    """選択肢用に有効なマスタを取得（カテゴリーと担当者は部門でしぼる）。"""
    ranks = Rank.query.filter_by(is_active=True).order_by(Rank.sort_order).all()
    kubun = Kubun.query.filter_by(is_active=True).order_by(Kubun.sort_order).all()
    categories = Category.query.filter_by(
        department_id=department.id, is_active=True
    ).order_by(Category.sort_order).all()
    # 担当者はその部門に所属するユーザー
    members = sorted(department.members, key=lambda u: u.user_id)
    return ranks, kubun, categories, members


def _collect_project_form(department, errors):
    """フォームから案件データを取り出して検証する（部門は department で固定）。"""
    data = {
        "accounting_month": _parse_month(request.form.get("accounting_month"), "計上月", errors),
        "assignee_user_id": _clean(request.form.get("assignee_user_id")),
        "kubun_id": _parse_fk(request.form.get("kubun_id")),
        "category_id": _parse_fk(request.form.get("category_id")),
        "project_name": _clean(request.form.get("project_name")),
        "rank_id": _parse_fk(request.form.get("rank_id")),
        "sales": _parse_int(request.form.get("sales"), "売上", errors),
        "cost": _parse_int(request.form.get("cost"), "仕入", errors),
        "estimated_hours": _parse_float(request.form.get("estimated_hours"), "見込み工数", errors),
        "actual_hours": _parse_float(request.form.get("actual_hours"), "対応工数", errors),
        "notes": _clean(request.form.get("notes")),
    }
    if not data["project_name"]:
        errors.append("案件名は必須です。")
    # 計上月がその期に属するか軽く確認（期外でも保存は許すが警告）
    return data


# ---------- 一覧（部門・計上月ごと） ----------
@projects_bp.route("")
@login_required
@password_change_guard
def list_projects():
    department, viewable = resolve_department()
    plan_type = _resolve_plan_type()
    if department is None:
        return render_template(
            "projects/list.html", department=None, viewable=[], months_data=[],
            period=fiscal.default_fiscal_period(), plan_type=plan_type,
            plan_type_labels=Project.PLAN_TYPE_LABELS, periods=fiscal.selectable_periods())

    period = resolve_period()
    projects = Project.query.filter_by(
        department_id=department.id, fiscal_period=period, plan_type=plan_type
    ).order_by(Project.accounting_month, Project.id).all()

    # 計上月ごとにグルーピング（期の12ヶ月順、該当なしの月も枠を作る）
    by_month = {}
    for p in projects:
        by_month.setdefault(p.accounting_month, []).append(p)

    months_data = []
    for m in fiscal.months(period):
        items = by_month.pop(m, [])
        months_data.append(_month_group(m, items))
    # 期外の月に計上されたものがあれば末尾に追加
    for m in sorted(by_month.keys()):
        months_data.append(_month_group(m, by_month[m]))

    return render_template(
        "projects/list.html", department=department, viewable=viewable,
        months_data=months_data, period=period,
        period_label=fiscal.period_label(period),
        periods=fiscal.selectable_periods(_existing_periods(department)),
        plan_type=plan_type, plan_type_labels=Project.PLAN_TYPE_LABELS,
        can_edit=current_user.can_edit_department(department.id) or current_user.role == 'user',
    )


def _month_group(month, items):
    """月見出しと小計（売上/仕入/売上総利益）をまとめた辞書を返す。"""
    return {
        "month": month,
        "label": fiscal.month_label(month),
        "cases": items,
        "sales": sum(p.sales or 0 for p in items),
        "cost": sum(p.cost or 0 for p in items),
        "gross": sum(p.gross_profit for p in items),
    }


# ---------- 新規登録 ----------
@projects_bp.route("/new", methods=["GET", "POST"])
@login_required
@password_change_guard
def new():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    # 登録できるのは、その部門の編集権を持つ人（sysadmin/該当admin）か、
    # その部門所属の一般ユーザー（自分を担当として登録）に限る。
    if not (current_user.can_edit_department(department.id)
            or current_user.role == "user"):
        abort(403)
    period = resolve_period()
    plan_type = _resolve_plan_type()
    ranks, kubun, categories, members = _masters(department)

    if request.method == "POST":
        errors = []
        data = _collect_project_form(department, errors)
        # 一般ユーザーは担当者を自分に固定（他人の案件は作れない）
        if current_user.role == "user":
            data["assignee_user_id"] = current_user.user_id
        _validate_assignee(data, department, errors)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("projects/form.html", mode="new", department=department,
                                   ranks=ranks, kubun=kubun, categories=categories,
                                   members=members, form=request.form, project=None,
                                   plan_type=plan_type, period=period,
                                   plan_type_labels=Project.PLAN_TYPE_LABELS)

        project = Project(department_id=department.id,
                          fiscal_period=period, plan_type=plan_type,
                          created_by=current_user.user_id,
                          updated_by=current_user.user_id, **data)
        db.session.add(project)
        db.session.commit()
        flash(f"案件 '{project.project_name}' を登録しました。", "success")
        return redirect(url_for("projects.list_projects", dept=department.id,
                                type=plan_type, period=period))

    # 既定の担当者
    default_form = {}
    if current_user.role == "user":
        default_form = {"assignee_user_id": current_user.user_id}
    return render_template("projects/form.html", mode="new", department=department,
                           ranks=ranks, kubun=kubun, categories=categories,
                           members=members, form=default_form, project=None,
                           plan_type=plan_type, period=period,
                           plan_type_labels=Project.PLAN_TYPE_LABELS)


# ---------- 編集 ----------
@projects_bp.route("/<int:project_id>/edit", methods=["GET", "POST"])
@login_required
@password_change_guard
def edit(project_id):
    project = db.session.get(Project, project_id)
    if project is None:
        abort(404)
    if not current_user.can_view_project(project):
        abort(403)
    department = project.department
    ranks, kubun, categories, members = _masters(department)

    if request.method == "POST":
        if not current_user.can_edit_project(project):
            abort(403)
        errors = []
        data = _collect_project_form(department, errors)
        if current_user.role == "user":
            # 一般は担当者を自分から外せない
            data["assignee_user_id"] = current_user.user_id
        _validate_assignee(data, department, errors)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("projects/form.html", mode="edit", department=department,
                                   ranks=ranks, kubun=kubun, categories=categories,
                                   members=members, form=request.form, project=project,
                                   plan_type=project.plan_type, period=project.fiscal_period,
                                   plan_type_labels=Project.PLAN_TYPE_LABELS)

        for key, value in data.items():
            setattr(project, key, value)
        project.updated_by = current_user.user_id
        db.session.commit()
        flash("案件を更新しました。", "success")
        return redirect(url_for("projects.list_projects", dept=department.id,
                                type=project.plan_type, period=project.fiscal_period))

    if not current_user.can_edit_project(project):
        abort(403)
    return render_template("projects/form.html", mode="edit", department=department,
                           ranks=ranks, kubun=kubun, categories=categories,
                           members=members, form=None, project=project,
                           plan_type=project.plan_type, period=project.fiscal_period,
                           plan_type_labels=Project.PLAN_TYPE_LABELS)


def _validate_assignee(data, department, errors):
    """担当者がその部門所属ユーザーか確認する。"""
    uid = data.get("assignee_user_id")
    if uid is None:
        return
    user = db.session.get(User, uid)
    if user is None or department.id not in user.department_ids:
        errors.append("担当者はその部門に所属するユーザーから選択してください。")


# ---------- 削除 ----------
@projects_bp.route("/<int:project_id>/delete", methods=["POST"])
@login_required
@password_change_guard
def delete(project_id):
    project = db.session.get(Project, project_id)
    if project is None:
        abort(404)
    if not current_user.can_edit_project(project):
        abort(403)
    dept_id = project.department_id
    plan_type = project.plan_type
    period = project.fiscal_period
    name = project.project_name
    db.session.delete(project)
    db.session.commit()
    flash(f"案件 '{name}' を削除しました。", "info")
    return redirect(url_for("projects.list_projects", dept=dept_id,
                            type=plan_type, period=period))


# ---------- 期初計画/中期計画 → 案件管理へコピー ----------
# コピー対象の列（監査列・plan_type・fiscal_period・部門は再設定するため除外）
_COPY_FIELDS = ("accounting_month", "assignee_user_id", "kubun_id", "category_id",
                "project_name", "rank_id", "sales", "cost",
                "estimated_hours", "actual_hours", "notes")


@projects_bp.route("/copy", methods=["POST"])
@login_required
@password_change_guard
def copy_to_management():
    """期初計画（または中期計画）の内容を案件管理へコピーする。

    対象部門×期の既存の案件管理データを全削除してから複製する（全置換）。
    実行できるのは対象部門の編集権を持つ管理者以上。
    """
    department, _ = resolve_department()
    if department is None:
        abort(403)
    if not current_user.can_edit_department(department.id):
        abort(403)
    period = resolve_period()
    source_type = request.form.get("source_type")
    if source_type not in (Project.PLAN_INITIAL, Project.PLAN_MIDTERM):
        abort(400)

    source_rows = Project.query.filter_by(
        department_id=department.id, fiscal_period=period, plan_type=source_type
    ).all()

    # 既存の案件管理データを全削除（全置換）
    Project.query.filter_by(
        department_id=department.id, fiscal_period=period,
        plan_type=Project.PLAN_MANAGEMENT
    ).delete(synchronize_session=False)

    for src in source_rows:
        data = {f: getattr(src, f) for f in _COPY_FIELDS}
        db.session.add(Project(
            department_id=department.id, fiscal_period=period,
            plan_type=Project.PLAN_MANAGEMENT,
            created_by=current_user.user_id, updated_by=current_user.user_id, **data))
    db.session.commit()

    label = Project.PLAN_TYPE_LABELS[source_type]
    flash(f"{label}から案件管理へ {len(source_rows)} 件をコピーしました"
          f"（既存の案件管理データは置き換えました）。", "success")
    return redirect(url_for("projects.list_projects", dept=department.id,
                            type=Project.PLAN_MANAGEMENT, period=period))


# ---------- エクスポート ----------
def _download(data: bytes, mimetype: str, ext: str, department, plan_type):
    label = Project.PLAN_TYPE_LABELS.get(plan_type, "案件管理")
    fname = f"{label}_{department.name}_{datetime.now().strftime('%Y%m%d')}.{ext}"
    resp = make_response(data)
    resp.headers["Content-Type"] = mimetype
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return resp


def _export_projects(department, period, plan_type):
    return Project.query.filter_by(
        department_id=department.id, fiscal_period=period, plan_type=plan_type
    ).order_by(Project.accounting_month, Project.id).all()


@projects_bp.route("/export.csv")
@login_required
@password_change_guard
def export_csv():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    plan_type = _resolve_plan_type()
    rows = _export_projects(department, resolve_period(), plan_type)
    data = exporters.to_csv(rows)
    return _download(data, "text/csv; charset=utf-8-sig", "csv", department, plan_type)


@projects_bp.route("/export.xlsx")
@login_required
@password_change_guard
def export_xlsx():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    plan_type = _resolve_plan_type()
    rows = _export_projects(department, resolve_period(), plan_type)
    data = exporters.to_xlsx(rows)
    return _download(
        data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx", department, plan_type)


@projects_bp.route("/export.pdf")
@login_required
@password_change_guard
def export_pdf():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    plan_type = _resolve_plan_type()
    label = Project.PLAN_TYPE_LABELS.get(plan_type, "案件管理")
    rows = _export_projects(department, resolve_period(), plan_type)
    data = exporters.to_pdf(rows, title=f"{label}（{department.name}）")
    return _download(data, "application/pdf", "pdf", department, plan_type)
