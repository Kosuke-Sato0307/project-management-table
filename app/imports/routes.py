"""案件のインポート（Excel/CSV）と部門テンプレートのダウンロード。

流れ: アップロード → プレビュー（検証）→ 確定。
検証で不正行が1つでもあれば取込全体を中止（オールオアナッシング）。
取込先は 部門 × 期(period) × plan_type（期初計画/中期計画/案件管理）。
テンプレートは部門ごとに生成し、第2営業部では担当者/区分/カテゴリー/確度を
Excelのドロップダウンで選択できるようにする。
"""
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, current_app, make_response, abort)
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Project, Rank, Kubun, Category, ProductCategory
from ..decorators import password_change_guard, resolve_department, resolve_period
from .. import importers

imports_bp = Blueprint("imports", __name__, url_prefix="/import")

ALLOWED_EXT = {"csv", "xlsx"}
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

# ドロップダウン付きテンプレートを提供する部門名
DROPDOWN_DEPARTMENTS = {"第2営業部"}


def _upload_dir() -> Path:
    d = Path(current_app.root_path).parent / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _saved_path(token, ext):
    return _upload_dir() / f"{token}.{ext}"


def _resolve_plan_type():
    """?type=initial|midterm|management を検証。既定は案件管理。"""
    pt = request.values.get("type")
    if pt in Project.PLAN_TYPES:
        return pt
    return Project.PLAN_MANAGEMENT


def _masters_maps(department):
    """検証用のマップ群を作る。

    戻り値: (member_map, kubun_map, category_map, rank_map, product_category_map)
      member_map:           {氏名: user_id}     （その部門のメンバー）
      kubun_map:            {区分名: id}
      category_map:         {コード or 表示名: id}（その部門）
      rank_map:             {確度名: id}
      product_category_map: {商品カテゴリ名: id} （その部門）
    """
    ranks = Rank.query.filter_by(is_active=True).order_by(Rank.sort_order).all()
    kubun = Kubun.query.filter_by(is_active=True).order_by(Kubun.sort_order).all()
    categories = Category.query.filter_by(
        department_id=department.id, is_active=True
    ).order_by(Category.sort_order).all()
    product_categories = ProductCategory.query.filter_by(
        department_id=department.id, is_active=True
    ).order_by(ProductCategory.sort_order).all()
    members = sorted(department.members, key=lambda u: u.user_id)

    member_map = {u.name: u.user_id for u in members}
    kubun_map = {k.name: k.id for k in kubun}
    category_map = {}
    for c in categories:
        category_map[c.code] = c.id
        category_map[c.display_name] = c.id
    rank_map = {r.name: r.id for r in ranks}
    product_category_map = {pc.name: pc.id for pc in product_categories}
    return (member_map, kubun_map, category_map, rank_map, product_category_map)


def _template_choices(department):
    """テンプレートのドロップダウン候補。対象外部門なら None（ドロップダウンなし）。"""
    if department.name not in DROPDOWN_DEPARTMENTS:
        return None
    ranks = Rank.query.filter_by(is_active=True).order_by(Rank.sort_order).all()
    kubun = Kubun.query.filter_by(is_active=True).order_by(Kubun.sort_order).all()
    categories = Category.query.filter_by(
        department_id=department.id, is_active=True
    ).order_by(Category.sort_order).all()
    product_categories = ProductCategory.query.filter_by(
        department_id=department.id, is_active=True
    ).order_by(ProductCategory.sort_order).all()
    members = sorted(department.members, key=lambda u: u.user_id)
    return {
        "assignee": [u.name for u in members],
        "kubun": [k.name for k in kubun],
        "category": [c.code for c in categories],
        "product_category": [pc.name for pc in product_categories],
        "rank": [r.name for r in ranks],
    }


def _require_edit(department):
    if not current_user.can_edit_department(department.id):
        abort(403)


def _download(data: bytes, mimetype: str, fname: str):
    resp = make_response(data)
    resp.headers["Content-Type"] = mimetype
    resp.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(fname)}"
    return resp


# ---------- アップロード画面 ----------
@imports_bp.route("")
@login_required
@password_change_guard
def upload_page():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    _require_edit(department)
    plan_type = _resolve_plan_type()
    period = resolve_period()
    return render_template(
        "imports/upload.html", department=department, plan_type=plan_type,
        period=period, plan_type_labels=Project.PLAN_TYPE_LABELS,
        headers=importers.TEMPLATE_HEADERS,
        has_dropdown=(department.name in DROPDOWN_DEPARTMENTS))


# ---------- テンプレDL ----------
@imports_bp.route("/template.csv")
@login_required
@password_change_guard
def template_csv():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    _require_edit(department)
    plan_type = _resolve_plan_type()
    label = Project.PLAN_TYPE_LABELS[plan_type]
    fname = f"{label}テンプレート_{department.name}.csv"
    return _download(importers.template_csv(), "text/csv; charset=utf-8-sig", fname)


@imports_bp.route("/template.xlsx")
@login_required
@password_change_guard
def template_xlsx():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    _require_edit(department)
    plan_type = _resolve_plan_type()
    label = Project.PLAN_TYPE_LABELS[plan_type]
    fname = f"{label}テンプレート_{department.name}.xlsx"
    data = importers.template_xlsx(_template_choices(department))
    return _download(
        data,
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        fname)


# ---------- プレビュー（アップロード＋検証） ----------
@imports_bp.route("/preview", methods=["POST"])
@login_required
@password_change_guard
def preview():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    _require_edit(department)
    plan_type = _resolve_plan_type()
    period = resolve_period()

    file = request.files.get("file")
    if file is None or file.filename == "":
        flash("ファイルを選択してください。", "danger")
        return redirect(url_for("imports.upload_page", dept=department.id,
                                type=plan_type, period=period))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        flash("対応形式は Excel(.xlsx) または CSV(.csv) です。", "danger")
        return redirect(url_for("imports.upload_page", dept=department.id,
                                type=plan_type, period=period))

    token = uuid.uuid4().hex
    path = _saved_path(token, ext)
    file.save(str(path))

    try:
        headers, data_rows = importers.parse_file(str(path), ext)
        results, errors = importers.validate(
            headers, data_rows, *_masters_maps(department))
    except Exception as e:  # 解析自体の失敗（壊れたファイル等）
        path.unlink(missing_ok=True)
        flash(f"ファイルを読み込めませんでした: {e}", "danger")
        return redirect(url_for("imports.upload_page", dept=department.id,
                                type=plan_type, period=period))

    ctx = {"department": department, "plan_type": plan_type, "period": period,
           "plan_type_labels": Project.PLAN_TYPE_LABELS}
    if errors:
        # 不正があるので取り込ませない。一時ファイルは破棄。
        path.unlink(missing_ok=True)
        session.pop("import_token", None)
        return render_template("imports/preview.html", errors=errors,
                               results=None, **ctx)

    # 問題なし → 確定に備えてトークンを保持
    session["import_token"] = token
    session["import_ext"] = ext
    session["import_dept"] = department.id
    session["import_period"] = period
    session["import_plan_type"] = plan_type
    return render_template("imports/preview.html", errors=None,
                           results=results, token=token, **ctx)


# ---------- 確定（反映） ----------
@imports_bp.route("/commit", methods=["POST"])
@login_required
@password_change_guard
def commit():
    department, _ = resolve_department()
    if department is None:
        abort(403)
    _require_edit(department)

    token = request.form.get("token", "")
    if not TOKEN_RE.match(token) or token != session.get("import_token"):
        flash("セッションが切れました。お手数ですが、もう一度アップロードしてください。", "danger")
        return redirect(url_for("imports.upload_page", dept=department.id))

    # セッションに保存した取込先を使う（改ざん防止）
    if session.get("import_dept") != department.id:
        abort(403)
    period = session.get("import_period")
    plan_type = session.get("import_plan_type", Project.PLAN_MANAGEMENT)
    ext = session.get("import_ext", "")
    path = _saved_path(token, ext)
    if not path.exists():
        flash("アップロードファイルが見つかりません。もう一度お試しください。", "danger")
        return redirect(url_for("imports.upload_page", dept=department.id,
                                type=plan_type, period=period))

    # 確定時にも再解析・再検証（安全のため）
    headers, data_rows = importers.parse_file(str(path), ext)
    results, errors = importers.validate(
        headers, data_rows, *_masters_maps(department))

    ctx = {"department": department, "plan_type": plan_type, "period": period,
           "plan_type_labels": Project.PLAN_TYPE_LABELS}
    if errors:
        path.unlink(missing_ok=True)
        session.pop("import_token", None)
        flash("内容が変更されたため取り込めませんでした。もう一度アップロードしてください。", "danger")
        return render_template("imports/preview.html", errors=errors,
                               results=None, **ctx)

    # 担当者名スナップショット用の {user_id: 氏名} マップ（削除後も氏名を残すため）
    name_by_id = {u.name: u.user_id for u in department.members}
    id_to_name = {uid: nm for nm, uid in name_by_id.items()}

    inserted = 0
    try:
        for r in results:
            assignee_name = id_to_name.get(r.data.get("assignee_user_id"))
            project = Project(department_id=department.id, fiscal_period=period,
                              plan_type=plan_type, created_by=current_user.user_id,
                              updated_by=current_user.user_id,
                              assignee_name=assignee_name, **r.data)
            db.session.add(project)
            inserted += 1
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"取り込み中にエラーが発生したため、すべて取り消しました: {e}", "danger")
        return redirect(url_for("imports.upload_page", dept=department.id,
                                type=plan_type, period=period))
    finally:
        path.unlink(missing_ok=True)
        for k in ("import_token", "import_ext", "import_dept",
                  "import_period", "import_plan_type"):
            session.pop(k, None)

    return render_template("imports/result.html", inserted=inserted, **ctx)
