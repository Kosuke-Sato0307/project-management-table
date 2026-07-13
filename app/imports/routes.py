"""案件のインポート（Excel/CSV）。

流れ: アップロード → プレビュー（検証）→ 確定。
検証で不正行が1つでもあれば取込全体を中止（オールオアナッシング）。
"""
import re
import uuid
from pathlib import Path

from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, current_app, make_response)
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Project, Status, Rank
from ..decorators import password_change_guard
from .. import importers

imports_bp = Blueprint("imports", __name__, url_prefix="/import")

ALLOWED_EXT = {"csv", "xlsx"}
TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _upload_dir() -> Path:
    d = Path(current_app.root_path).parent / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _masters_maps():
    statuses = Status.query.all()
    ranks = Rank.query.all()
    return ({s.name: s.id for s in statuses}, {r.name: r.id for r in ranks})


def _existing_nos():
    return {row[0] for row in db.session.query(Project.project_no).all()}


def _saved_path(token, ext):
    return _upload_dir() / f"{token}.{ext}"


# ---------- アップロード画面 ----------
@imports_bp.route("")
@login_required
@password_change_guard
def upload_page():
    return render_template("imports/upload.html", headers=importers.TEMPLATE_HEADERS)


# ---------- テンプレDL ----------
@imports_bp.route("/template.csv")
@login_required
@password_change_guard
def template_csv():
    resp = make_response(importers.template_csv())
    resp.headers["Content-Type"] = "text/csv; charset=utf-8-sig"
    resp.headers["Content-Disposition"] = "attachment; filename*=UTF-8''%E6%A1%88%E4%BB%B6%E5%8F%96%E8%BE%BC%E3%83%86%E3%83%B3%E3%83%97%E3%83%AC.csv"
    return resp


@imports_bp.route("/template.xlsx")
@login_required
@password_change_guard
def template_xlsx():
    resp = make_response(importers.template_xlsx())
    resp.headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    resp.headers["Content-Disposition"] = "attachment; filename*=UTF-8''%E6%A1%88%E4%BB%B6%E5%8F%96%E8%BE%BC%E3%83%86%E3%83%B3%E3%83%97%E3%83%AC.xlsx"
    return resp


# ---------- プレビュー（アップロード＋検証） ----------
@imports_bp.route("/preview", methods=["POST"])
@login_required
@password_change_guard
def preview():
    file = request.files.get("file")
    if file is None or file.filename == "":
        flash("ファイルを選択してください。", "danger")
        return redirect(url_for("imports.upload_page"))

    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXT:
        flash("対応形式は Excel(.xlsx) または CSV(.csv) です。", "danger")
        return redirect(url_for("imports.upload_page"))

    token = uuid.uuid4().hex
    path = _saved_path(token, ext)
    file.save(str(path))

    try:
        headers, data_rows = importers.parse_file(str(path), ext)
        status_map, rank_map = _masters_maps()
        results, errors = importers.validate(
            headers, data_rows, _existing_nos(), status_map, rank_map)
    except Exception as e:  # 解析自体の失敗（壊れたファイル等）
        path.unlink(missing_ok=True)
        flash(f"ファイルを読み込めませんでした: {e}", "danger")
        return redirect(url_for("imports.upload_page"))

    if errors:
        # 不正があるので取り込ませない。一時ファイルは破棄。
        path.unlink(missing_ok=True)
        session.pop("import_token", None)
        return render_template("imports/preview.html",
                               errors=errors, results=None)

    # 問題なし → 確定に備えてトークンを保持
    session["import_token"] = token
    session["import_ext"] = ext
    new_count = sum(1 for r in results if r.action == "new")
    update_count = sum(1 for r in results if r.action == "update")
    return render_template("imports/preview.html", errors=None,
                           results=results, new_count=new_count,
                           update_count=update_count, token=token)


# ---------- 確定（反映） ----------
@imports_bp.route("/commit", methods=["POST"])
@login_required
@password_change_guard
def commit():
    token = request.form.get("token", "")
    dup_mode = request.form.get("dup_mode", "skip")
    if dup_mode not in ("skip", "overwrite"):
        dup_mode = "skip"

    if not TOKEN_RE.match(token) or token != session.get("import_token"):
        flash("セッションが切れました。お手数ですが、もう一度アップロードしてください。", "danger")
        return redirect(url_for("imports.upload_page"))

    ext = session.get("import_ext", "")
    path = _saved_path(token, ext)
    if not path.exists():
        flash("アップロードファイルが見つかりません。もう一度お試しください。", "danger")
        return redirect(url_for("imports.upload_page"))

    # 確定時にも再解析・再検証（安全のため）
    headers, data_rows = importers.parse_file(str(path), ext)
    status_map, rank_map = _masters_maps()
    results, errors = importers.validate(
        headers, data_rows, _existing_nos(), status_map, rank_map)

    if errors:
        path.unlink(missing_ok=True)
        session.pop("import_token", None)
        flash("内容が変更されたため取り込めませんでした。もう一度アップロードしてください。", "danger")
        return render_template("imports/preview.html", errors=errors, results=None)

    inserted = updated = skipped = 0
    try:
        for r in results:
            if r.action == "update":
                if dup_mode == "skip":
                    skipped += 1
                    continue
                project = db.session.get(Project, r.data["project_no"])
                for k, v in r.data.items():
                    if k == "project_no":
                        continue
                    setattr(project, k, v)
                project.updated_by = current_user.user_id
                updated += 1
            else:
                project = Project(created_by=current_user.user_id,
                                  updated_by=current_user.user_id, **r.data)
                db.session.add(project)
                inserted += 1
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"取り込み中にエラーが発生したため、すべて取り消しました: {e}", "danger")
        return redirect(url_for("imports.upload_page"))
    finally:
        path.unlink(missing_ok=True)
        session.pop("import_token", None)
        session.pop("import_ext", None)

    return render_template("imports/result.html", inserted=inserted,
                           updated=updated, skipped=skipped, dup_mode=dup_mode)
