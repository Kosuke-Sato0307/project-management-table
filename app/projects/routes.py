"""案件の一覧・検索・詳細・登録・編集・削除。

閲覧〜編集〜削除は全ログインユーザーが可能（要件どおり）。
"""
from datetime import datetime, date

from urllib.parse import quote

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, make_response)
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Project, Status, Rank, Department
from ..decorators import password_change_guard
from .. import exporters

projects_bp = Blueprint("projects", __name__, url_prefix="/projects")

# 並び替え可能な列（外部入力を直接カラムにしないためのホワイトリスト）
SORTABLE = {
    "project_no": Project.project_no,
    "project_name": Project.project_name,
    "customer_name": Project.customer_name,
    "amount_excl_tax": Project.amount_excl_tax,
    "completion_month": Project.completion_month,
    "order_date": Project.order_date,
    "updated_at": Project.updated_at,
}
PER_PAGE = 50


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
    # 全角や桁区切りカンマも許容
    normalized = value.replace(",", "").replace("，", "").translate(
        str.maketrans("０１２３４５６７８９", "0123456789"))
    try:
        return int(normalized)
    except ValueError:
        errors.append(f"{field_label}は数字で入力してください。")
        return None


def _parse_date(value, field_label, errors):
    value = _clean(value)
    if value is None:
        return None
    # yyyy/m/d と yyyy-mm-dd の両方を受理
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    errors.append(f"{field_label}は 2026/7/5 の形式で入力してください。")
    return None


def _parse_month(value, field_label, errors):
    """完成月。yyyy/m または yyyy-mm を受理し、保存用に 'YYYY-MM' へ正規化。"""
    value = _clean(value)
    if value is None:
        return None
    normalized = value.replace("/", "-")
    try:
        dt = datetime.strptime(normalized, "%Y-%m")
        return dt.strftime("%Y-%m")   # ゼロ埋め正規化（並び替え/範囲検索用）
    except ValueError:
        errors.append(f"{field_label}は 2026/7 の形式で入力してください。")
        return None


def normalize_month(value):
    """検索フィルタ用: 'yyyy/m' や 'yyyy-m' を 'YYYY-MM' に正規化（不正はNone）。"""
    value = _clean(value)
    if value is None:
        return None
    try:
        return datetime.strptime(value.replace("/", "-"), "%Y-%m").strftime("%Y-%m")
    except ValueError:
        return None


def _parse_fk(value):
    """ステータス/確度の選択値（空 or 数値）。"""
    value = _clean(value)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _collect_project_form(errors):
    """フォームから案件データを取り出して検証する。"""
    data = {
        "project_name": _clean(request.form.get("project_name")),
        "customer_name": _clean(request.form.get("customer_name")),
        "status_id": _parse_fk(request.form.get("status_id")),
        "rank_id": _parse_fk(request.form.get("rank_id")),
        "estimate_no": _clean(request.form.get("estimate_no")),
        "amount_excl_tax": _parse_int(request.form.get("amount_excl_tax"), "金額(税抜)", errors),
        "completion_month": _parse_month(request.form.get("completion_month"), "完成月", errors),
        "order_date": _parse_date(request.form.get("order_date"), "受注日", errors),
        "sales_rep": _clean(request.form.get("sales_rep")),
        "department": _clean(request.form.get("department")),
        "notes": _clean(request.form.get("notes")),
    }
    if not data["project_name"]:
        errors.append("案件名は必須です。")
    return data


def _masters():
    """選択肢用に有効なマスタを取得。"""
    statuses = Status.query.filter_by(is_active=True).order_by(Status.sort_order).all()
    ranks = Rank.query.filter_by(is_active=True).order_by(Rank.sort_order).all()
    departments = Department.query.filter_by(is_active=True).order_by(Department.sort_order).all()
    return statuses, ranks, departments


def build_filtered_query(args):
    """検索条件と並び順を適用したクエリを返す（一覧とエクスポートで共用）。

    戻り値: (query, filters_dict, sort, direction)
    """
    f = {
        "no": _clean(args.get("no")),
        "name": _clean(args.get("name")),
        "customer": _clean(args.get("customer")),
        "status_id": _parse_fk(args.get("status_id")),
        "rank_id": _parse_fk(args.get("rank_id")),
        "month_from": _clean(args.get("month_from")),
        "month_to": _clean(args.get("month_to")),
        "amount_min": _clean(args.get("amount_min")),
        "amount_max": _clean(args.get("amount_max")),
    }

    query = Project.query
    if f["no"]:
        query = query.filter(Project.project_no.contains(f["no"]))
    if f["name"]:
        query = query.filter(Project.project_name.contains(f["name"]))
    if f["customer"]:
        query = query.filter(Project.customer_name.contains(f["customer"]))
    if f["status_id"]:
        query = query.filter(Project.status_id == f["status_id"])
    if f["rank_id"]:
        query = query.filter(Project.rank_id == f["rank_id"])
    mf = normalize_month(f["month_from"])
    mt = normalize_month(f["month_to"])
    if mf:
        query = query.filter(Project.completion_month >= mf)
    if mt:
        query = query.filter(Project.completion_month <= mt)
    if f["amount_min"] and f["amount_min"].isdigit():
        query = query.filter(Project.amount_excl_tax >= int(f["amount_min"]))
    if f["amount_max"] and f["amount_max"].isdigit():
        query = query.filter(Project.amount_excl_tax <= int(f["amount_max"]))

    sort = args.get("sort", "updated_at")
    direction = args.get("dir", "desc")
    col = SORTABLE.get(sort, Project.updated_at)
    query = query.order_by(col.asc() if direction == "asc" else col.desc())
    return query, f, sort, direction


# ---------- 一覧・検索 ----------
@projects_bp.route("")
@login_required
@password_change_guard
def list_projects():
    query, f, sort, direction = build_filtered_query(request.args)
    page = request.args.get("page", 1, type=int)
    pagination = query.paginate(page=page, per_page=PER_PAGE, error_out=False)

    statuses, ranks, departments = _masters()
    return render_template("projects/list.html",
                           pagination=pagination, projects=pagination.items,
                           filters=f, statuses=statuses, ranks=ranks,
                           departments=departments,
                           sort=sort, direction=direction)


# ---------- 詳細 ----------
@projects_bp.route("/<project_no>")
@login_required
@password_change_guard
def detail(project_no):
    project = db.session.get(Project, project_no)
    if project is None:
        abort(404)
    return render_template("projects/detail.html", project=project)


# ---------- 新規登録 ----------
@projects_bp.route("/new", methods=["GET", "POST"])
@login_required
@password_change_guard
def new():
    statuses, ranks, departments = _masters()
    if request.method == "POST":
        errors = []
        project_no = _clean(request.form.get("project_no"))
        if not project_no:
            errors.append("案件番号は必須です。")
        elif db.session.get(Project, project_no):
            errors.append(f"案件番号 '{project_no}' は既に登録されています。")

        data = _collect_project_form(errors)
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("projects/form.html", mode="new",
                                   statuses=statuses, ranks=ranks,
                                   departments=departments,
                                   form=request.form, project=None)

        project = Project(project_no=project_no,
                          created_by=current_user.user_id,
                          updated_by=current_user.user_id, **data)
        db.session.add(project)
        db.session.commit()
        flash(f"案件 '{project_no}' を登録しました。", "success")
        return redirect(url_for("projects.detail", project_no=project_no))

    return render_template("projects/form.html", mode="new", statuses=statuses,
                           ranks=ranks, departments=departments, form={}, project=None)


# ---------- 編集 ----------
@projects_bp.route("/<project_no>/edit", methods=["GET", "POST"])
@login_required
@password_change_guard
def edit(project_no):
    project = db.session.get(Project, project_no)
    if project is None:
        abort(404)
    statuses, ranks, departments = _masters()

    if request.method == "POST":
        errors = []
        data = _collect_project_form(errors)

        # 案件番号は主キーのため通常は変更不可。ただし管理者のみ変更を許可する。
        # 管理者フォームでは project_no 欄を送信するため、送信された場合のみ検証する。
        new_no = project_no
        if current_user.is_admin and "project_no" in request.form:
            submitted_no = _clean(request.form.get("project_no"))
            if not submitted_no:
                errors.append("案件番号は必須です。")
            elif submitted_no != project_no and db.session.get(Project, submitted_no):
                errors.append(f"案件番号 '{submitted_no}' は既に登録されています。")
            else:
                new_no = submitted_no

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("projects/form.html", mode="edit",
                                   statuses=statuses, ranks=ranks,
                                   departments=departments,
                                   form=request.form, project=project)

        for key, value in data.items():
            setattr(project, key, value)
        if new_no != project_no:
            project.project_no = new_no   # 主キー更新（子参照は無いため安全）
        project.updated_by = current_user.user_id
        db.session.commit()
        flash("案件を更新しました。", "success")
        return redirect(url_for("projects.detail", project_no=new_no))

    return render_template("projects/form.html", mode="edit", statuses=statuses,
                           ranks=ranks, departments=departments,
                           form=None, project=project)


# ---------- エクスポート ----------
def _download(data: bytes, mimetype: str, ext: str):
    """バイト列をダウンロードレスポンスにして返す（日本語ファイル名対応）。"""
    fname = f"案件一覧_{datetime.now().strftime('%Y%m%d')}.{ext}"
    resp = make_response(data)
    resp.headers["Content-Type"] = mimetype
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return resp


@projects_bp.route("/export.csv")
@login_required
@password_change_guard
def export_csv():
    query, _, _, _ = build_filtered_query(request.args)
    data = exporters.to_csv(query.all())
    return _download(data, "text/csv; charset=utf-8-sig", "csv")


@projects_bp.route("/export.xlsx")
@login_required
@password_change_guard
def export_xlsx():
    query, _, _, _ = build_filtered_query(request.args)
    data = exporters.to_xlsx(query.all())
    return _download(
        data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xlsx")


@projects_bp.route("/export.pdf")
@login_required
@password_change_guard
def export_pdf():
    query, _, _, _ = build_filtered_query(request.args)
    data = exporters.to_pdf(query.all())
    return _download(data, "application/pdf", "pdf")


# ---------- 削除 ----------
@projects_bp.route("/<project_no>/delete", methods=["POST"])
@login_required
@password_change_guard
def delete(project_no):
    project = db.session.get(Project, project_no)
    if project is None:
        abort(404)
    db.session.delete(project)
    db.session.commit()
    flash(f"案件 '{project_no}' を削除しました。", "info")
    return redirect(url_for("projects.list_projects"))
