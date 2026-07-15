"""数字まとめ（案件管理表とは別タブ）。

部門スコープ・59期対象。サブタブ:
  - 予実まとめ(yojitsu): 実績(○)/期初計画/差異/達成率
  - 損益まとめ(soneki): 売上/仕入/売上総利益/粗利率 + 販管費対比（実績○ベース）
  - カテゴリー別(category): 通期
  - 確度別(rank): 通期・全案件
  - 販管費入力(sga): 部門×12ヶ月の手入力（編集権のある部門のみ）
"""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort)
from flask_login import login_required, current_user

from ..extensions import db
from ..models import Project, Rank, Category, ProductCategory, Sga
from ..decorators import password_change_guard, resolve_department, resolve_period
from .. import fiscal
from . import calc

analytics_bp = Blueprint("analytics", __name__, url_prefix="/analytics")


def _load_projects(department, period):
    return Project.query.filter_by(
        department_id=department.id, fiscal_period=period
    ).all()


def _sga_by_month(department, period):
    rows = Sga.query.filter_by(department_id=department.id, fiscal_period=period).all()
    return {r.month: (r.amount or 0) for r in rows}


def _common(view):
    """各画面共通の部門・期・タブ情報を返す。department が None なら (None, ctx)。"""
    department, viewable = resolve_department()
    period = resolve_period()
    extra = None
    if department is not None:
        rows = db.session.query(Project.fiscal_period).filter_by(
            department_id=department.id).distinct().all()
        extra = [r[0] for r in rows]
    ctx = {
        "department": department,
        "viewable": viewable,
        "period": period,
        "period_label": fiscal.period_label(period),
        "periods": fiscal.selectable_periods(extra),
        "active_view": view,
    }
    return department, ctx


@analytics_bp.route("")
@login_required
@password_change_guard
def index():
    return redirect(url_for("analytics.yojitsu"))


@analytics_bp.route("/yojitsu")
@login_required
@password_change_guard
def yojitsu():
    department, ctx = _common("yojitsu")
    if department is None:
        return render_template("analytics/empty.html", **ctx)
    gran = request.args.get("gran", "full")
    if gran not in calc.GRAN_LABELS:
        gran = "full"
    projects = _load_projects(department, ctx["period"])
    tables = calc.yojitsu(department, projects, ctx["period"], gran)
    return render_template("analytics/yojitsu.html", gran=gran, tables=tables,
                           gran_labels=calc.GRAN_LABELS, gran_order=calc.GRAN_ORDER, **ctx)


@analytics_bp.route("/soneki")
@login_required
@password_change_guard
def soneki():
    department, ctx = _common("soneki")
    if department is None:
        return render_template("analytics/empty.html", **ctx)
    gran = request.args.get("gran", "full")
    if gran not in calc.GRAN_LABELS:
        gran = "full"
    projects = _load_projects(department, ctx["period"])
    sga_map = _sga_by_month(department, ctx["period"])
    data = calc.soneki(department, projects, ctx["period"], gran, sga_map)
    return render_template("analytics/soneki.html", gran=gran, data=data,
                           gran_labels=calc.GRAN_LABELS, gran_order=calc.GRAN_ORDER, **ctx)


@analytics_bp.route("/category")
@login_required
@password_change_guard
def category():
    department, ctx = _common("category")
    if department is None:
        return render_template("analytics/empty.html", **ctx)
    projects = _load_projects(department, ctx["period"])
    categories = Category.query.filter_by(
        department_id=department.id, is_active=True
    ).order_by(Category.sort_order).all()
    data = calc.by_category(categories, projects)
    return render_template("analytics/category.html", data=data, **ctx)


@analytics_bp.route("/product-category")
@login_required
@password_change_guard
def product_category():
    department, ctx = _common("product_category")
    if department is None:
        return render_template("analytics/empty.html", **ctx)
    projects = _load_projects(department, ctx["period"])
    product_categories = ProductCategory.query.filter_by(
        department_id=department.id, is_active=True
    ).order_by(ProductCategory.sort_order).all()
    data = calc.by_product_category(product_categories, projects)
    return render_template("analytics/product_category.html", data=data, **ctx)


@analytics_bp.route("/rank")
@login_required
@password_change_guard
def rank():
    department, ctx = _common("rank")
    if department is None:
        return render_template("analytics/empty.html", **ctx)
    projects = _load_projects(department, ctx["period"])
    ranks = Rank.query.filter_by(is_active=True).order_by(Rank.sort_order).all()
    data = calc.by_rank(ranks, projects)
    return render_template("analytics/rank.html", data=data, **ctx)


# ---------- 販管費入力 ----------
@analytics_bp.route("/sga", methods=["GET", "POST"])
@login_required
@password_change_guard
def sga():
    department, ctx = _common("sga")
    if department is None:
        return render_template("analytics/empty.html", **ctx)
    period = ctx["period"]
    can_edit = current_user.can_edit_department(department.id)
    months = fiscal.months(period)

    if request.method == "POST":
        if not can_edit:
            abort(403)
        existing = {r.month: r for r in
                    Sga.query.filter_by(department_id=department.id,
                                        fiscal_period=period).all()}
        for m in months:
            raw = (request.form.get(f"m_{m}") or "").strip()
            raw = raw.replace(",", "").replace("，", "")
            amount = 0
            if raw:
                try:
                    amount = int(raw)
                except ValueError:
                    flash(f"{fiscal.month_label(m)} の販管費は数字で入力してください。", "danger")
                    return redirect(url_for("analytics.sga", dept=department.id, period=period))
            row = existing.get(m)
            if row is None:
                db.session.add(Sga(department_id=department.id, fiscal_period=period,
                                   month=m, amount=amount))
            else:
                row.amount = amount
        db.session.commit()
        flash("販管費を保存しました。", "success")
        return redirect(url_for("analytics.sga", dept=department.id, period=period))

    sga_map = _sga_by_month(department, period)
    # 集計（四半期/半期/通期）
    quarters = [(fiscal.QUARTER_LABELS[q],
                 sum(sga_map.get(m, 0) for m in fiscal.quarter_months(q, period)))
                for q in (1, 2, 3, 4)]
    halves = [(fiscal.HALF_LABELS[h],
               sum(sga_map.get(m, 0) for m in fiscal.half_months(h, period)))
              for h in (1, 2)]
    full = sum(sga_map.values())
    month_rows = [(m, fiscal.month_label(m), sga_map.get(m, 0)) for m in months]
    return render_template("analytics/sga.html", can_edit=can_edit,
                           month_rows=month_rows, quarters=quarters,
                           halves=halves, full=full, **ctx)
