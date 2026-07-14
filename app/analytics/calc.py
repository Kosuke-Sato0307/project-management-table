"""数字まとめ（予実/損益/カテゴリー別/確度別）の集計ロジック。

集計の前提（ユーザー確定事項）:
  - 期初計画値 = plan_type が「期初計画」(initial) の案件。
  - 中期計画値 = plan_type が「中期計画」(midterm) の案件。
  - 実績値 = plan_type が「案件管理」(management) かつ 確度「○」（受注確定）の案件。
  - 売上総利益 = 売上 − 仕入（Project.gross_profit）。
  - 損益まとめは実績（案件管理×確度○）ベース。確度別まとめは案件管理の全案件が対象。

集計は部門内の案件をメモリに読み込み、月→四半期/半期/通期のバケットで合算する。
"""
from __future__ import annotations

from .. import fiscal


# ---- 案件のデータセット/実績判定（plan_type ベース） ----
def _is_initial(p) -> bool:
    """期初計画の案件か。"""
    return p.plan_type == "initial"


def _is_midterm(p) -> bool:
    """中期計画の案件か。"""
    return p.plan_type == "midterm"


def _is_actual(p) -> bool:
    """実績（案件管理 かつ 確度○）か。"""
    return p.plan_type == "management" and p.is_actual

# 指標: (キー, 見出し)
METRICS = [("sales", "売上"), ("cost", "仕入"), ("gross", "売上総利益")]

GRAN_LABELS = {"month": "月次", "quarter": "四半期", "half": "半期", "full": "通期"}
GRAN_ORDER = ["month", "quarter", "half", "full"]


def _mval(p, metric: str) -> int:
    if metric == "sales":
        return p.sales or 0
    if metric == "cost":
        return p.cost or 0
    return p.gross_profit  # gross


def buckets(period: int, gran: str):
    """(ラベル, 月リスト) のリストを返す。"""
    if gran == "month":
        return [(fiscal.month_label(m), [m]) for m in fiscal.months(period)]
    if gran == "quarter":
        return [(fiscal.QUARTER_LABELS[q], fiscal.quarter_months(q, period))
                for q in (1, 2, 3, 4)]
    if gran == "half":
        return [(fiscal.HALF_LABELS[h], fiscal.half_months(h, period))
                for h in (1, 2)]
    return [("通期", fiscal.months(period))]  # full


def _rate(actual, plan):
    """達成率（%）。計画0なら None。"""
    if not plan:
        return None
    return actual / plan * 100.0


def _margin(gross, sales):
    """粗利率（%）。売上0なら None。"""
    if not sales:
        return None
    return gross / sales * 100.0


def user_entries(department, projects):
    """(user_id, 表示名) のリスト。部門メンバー＋担当者未設定を含む。"""
    entries = [(u.user_id, u.name) for u in
               sorted(department.members, key=lambda u: u.user_id)]
    # 担当者未設定の案件があれば末尾に加える
    if any(p.assignee_user_id is None for p in projects):
        entries.append((None, "(担当者未設定)"))
    return entries


# ---------- (A) 予実まとめ ----------
def yojitsu(department, projects, period, gran):
    """指標ごとにテーブルを作る。

    戻り値: [{metric, headers[], rows[{name, cells[{plan,actual,var,rate}]}], total{...}}]
    cells は bucket 順。
    """
    bks = buckets(period, gran)
    users = user_entries(department, projects)
    tables = []
    for mkey, mlabel in METRICS:
        rows = []
        # 合計セル（各バケット）
        total_cells = [{"plan": 0, "midterm": 0, "actual": 0} for _ in bks]
        for uid, uname in users:
            cells = []
            for bi, (_, months) in enumerate(bks):
                plan = midterm = actual = 0
                for p in projects:
                    if p.assignee_user_id != uid:
                        continue
                    if p.accounting_month not in months:
                        continue
                    val = _mval(p, mkey)
                    if _is_initial(p):
                        plan += val
                    if _is_midterm(p):
                        midterm += val
                    if _is_actual(p):
                        actual += val
                total_cells[bi]["plan"] += plan
                total_cells[bi]["midterm"] += midterm
                total_cells[bi]["actual"] += actual
                cells.append(_yojitsu_cell(plan, midterm, actual))
            rows.append({"name": uname, "cells": cells})
        total_row = {"name": "合計",
                     "cells": [_yojitsu_cell(c["plan"], c["midterm"], c["actual"])
                               for c in total_cells]}
        tables.append({
            "metric": mlabel,
            "headers": [label for label, _ in bks],
            "rows": rows,
            "total": total_row,
        })
    return tables


def _yojitsu_cell(plan, midterm, actual):
    return {
        "plan": plan,
        "midterm": midterm,
        "actual": actual,
        "var": actual - plan,
        "rate": _rate(actual, plan),
    }


# ---------- (B) 損益まとめ ----------
def soneki(department, projects, period, gran, sga_by_month):
    """実績（確度○）ベースの損益まとめ。

    戻り値: {
      headers[], rows[{name, cells[{sales,cost,gross,margin}]}],
      total[cell...], sga[amount...], balance[amount...]
    }
    販管費(sga)・差引(balance)は部門合計に対する行。
    """
    bks = buckets(period, gran)
    users = user_entries(department, projects)
    rows = []
    total_cells = [{"sales": 0, "cost": 0, "gross": 0} for _ in bks]
    for uid, uname in users:
        cells = []
        for bi, (_, months) in enumerate(bks):
            s = c = g = 0
            for p in projects:
                if p.assignee_user_id != uid or not _is_actual(p):
                    continue
                if p.accounting_month not in months:
                    continue
                s += p.sales or 0
                c += p.cost or 0
                g += p.gross_profit
            total_cells[bi]["sales"] += s
            total_cells[bi]["cost"] += c
            total_cells[bi]["gross"] += g
            cells.append({"sales": s, "cost": c, "gross": g, "margin": _margin(g, s)})
        rows.append({"name": uname, "cells": cells})

    total_row = [{"sales": t["sales"], "cost": t["cost"], "gross": t["gross"],
                  "margin": _margin(t["gross"], t["sales"])} for t in total_cells]

    sga_cells = []
    balance_cells = []
    for bi, (_, months) in enumerate(bks):
        sga_amt = sum(sga_by_month.get(m, 0) for m in months)
        sga_cells.append(sga_amt)
        balance_cells.append(total_cells[bi]["gross"] - sga_amt)

    return {
        "headers": [label for label, _ in bks],
        "rows": rows,
        "total": total_row,
        "sga": sga_cells,
        "balance": balance_cells,
    }


# ---------- (C) カテゴリー別（通期） ----------
def by_category(categories, projects):
    """カテゴリーごとに 売上計画/売上実績/売上総利益計画/売上総利益実績（通期）。"""
    rows = []
    totals = {"sales_plan": 0, "sales_actual": 0, "gross_plan": 0, "gross_actual": 0}
    # カテゴリー未設定を拾うため cat_id -> label のマップ
    cat_map = {c.id: c.display_name for c in categories}
    order = list(cat_map.keys()) + [None]
    labels = dict(cat_map)
    labels[None] = "(カテゴリー未設定)"

    grouped = {cid: [] for cid in order}
    for p in projects:
        key = p.category_id if p.category_id in cat_map else None
        grouped.setdefault(key, []).append(p)

    for cid in order:
        items = grouped.get(cid, [])
        if not items and cid is None:
            continue
        r = {
            "name": labels[cid],
            "sales_plan": sum((p.sales or 0) for p in items if _is_initial(p)),
            "sales_actual": sum((p.sales or 0) for p in items if _is_actual(p)),
            "gross_plan": sum(p.gross_profit for p in items if _is_initial(p)),
            "gross_actual": sum(p.gross_profit for p in items if _is_actual(p)),
        }
        for k in totals:
            totals[k] += r[k]
        rows.append(r)
    return {"rows": rows, "total": {"name": "合計", **totals}}


# ---------- (D) 確度別（通期・案件管理の全案件） ----------
def by_rank(ranks, projects):
    """確度ごとに 売上/仕入/売上総利益/粗利率（通期・案件管理の全案件）。

    計画（期初計画/中期計画）の確度は混ぜず、案件管理(management)のみを対象にする。
    """
    rows = []
    totals = {"sales": 0, "cost": 0, "gross": 0}
    order = [(r.id, r.name) for r in ranks] + [(None, "(確度未設定)")]
    rank_ids = {r.id for r in ranks}
    grouped = {}
    for p in projects:
        if p.plan_type != "management":
            continue
        key = p.rank_id if p.rank_id in rank_ids else None
        grouped.setdefault(key, []).append(p)

    for rid, rname in order:
        items = grouped.get(rid, [])
        if not items and rid is None:
            continue
        s = sum((p.sales or 0) for p in items)
        c = sum((p.cost or 0) for p in items)
        g = sum(p.gross_profit for p in items)
        totals["sales"] += s
        totals["cost"] += c
        totals["gross"] += g
        rows.append({"name": rname, "sales": s, "cost": c, "gross": g,
                     "margin": _margin(g, s)})
    total = {"name": "合計", **totals, "margin": _margin(totals["gross"], totals["sales"])}
    return {"rows": rows, "total": total}
