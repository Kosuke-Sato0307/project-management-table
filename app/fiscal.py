"""会計期（決算期）に関するヘルパー。

弊社は「9月始まり・8月締め」のサイクル。来期 = 59期 は 2026-09 〜 2027-08。
案件・販管費は 'YYYY-MM' 形式の月（計上月）を持ち、ここで月 → 四半期/半期/通期
のまとめ方を一元的に定義する。将来の期（60期以降）も同じロジックで扱える。

用語:
  - 期(period): 59, 60, ... の整数。
  - 上期/下期(half): 上期 = Q1+Q2、下期 = Q3+Q4。
  - クォーター(quarter): Q1=9-11, Q2=12-2, Q3=3-5, Q4=6-8。
"""
from __future__ import annotations

from datetime import date

# アプリが扱う最小の期（フロア値）。59期リニューアルで運用開始したため、
# これより前の期は選択肢に出さない。既定値の下限にも使う。
CURRENT_FISCAL_PERIOD = 59

# 期の開始月（9月始まり）
FISCAL_START_MONTH = 9

# アンカー: 59期は 2026年9月開始。start_year(period) = 2026 + (period - 59)
_ANCHOR_PERIOD = 59
_ANCHOR_START_YEAR = 2026


def period_start_year(period: int = CURRENT_FISCAL_PERIOD) -> int:
    """その期が始まる西暦年（=9月の年）を返す。59期 -> 2026。"""
    return _ANCHOR_START_YEAR + (period - _ANCHOR_PERIOD)


def period_label(period: int = CURRENT_FISCAL_PERIOD) -> str:
    """'59期（2026/9〜2027/8）' のような表示ラベル。"""
    sy = period_start_year(period)
    return f"{period}期（{sy}/9〜{sy + 1}/8）"


def months(period: int = CURRENT_FISCAL_PERIOD) -> list[str]:
    """その期の12ヶ月を並び順で返す。['2026-09', ..., '2027-08']。"""
    sy = period_start_year(period)
    result = []
    for i in range(12):
        m0 = (FISCAL_START_MONTH - 1) + i           # 0-based month index from Jan
        year = sy + m0 // 12
        month = m0 % 12 + 1
        result.append(f"{year:04d}-{month:02d}")
    return result


def period_of_month(month: str) -> int | None:
    """'YYYY-MM' がどの期に属するかを返す（不正なら None）。"""
    try:
        y, m = _split(month)
    except (ValueError, TypeError):
        return None
    # 9〜12月はその年から始まる期、1〜8月は前年から始まる期。
    start_year = y if m >= FISCAL_START_MONTH else y - 1
    return _ANCHOR_PERIOD + (start_year - _ANCHOR_START_YEAR)


def default_fiscal_period(today: date | None = None) -> int:
    """画面の既定として表示する期を返す。

    ルール: max(59, 今日が属する期)。9月1日を境に自動で+1される。
      - 2026-07（本来58期） -> 59（試験運用のため59期を先行表示、59でフロア）
      - 2026-09〜2027-08     -> 59
      - 2027-09〜2028-08     -> 60
      - 2028-09〜2029-08     -> 61 …
    """
    today = today or date.today()
    ym = f"{today.year:04d}-{today.month:02d}"
    natural = period_of_month(ym) or CURRENT_FISCAL_PERIOD
    return max(CURRENT_FISCAL_PERIOD, natural)


def selectable_periods(extra: list[int] | None = None) -> list[int]:
    """期セレクタに出す期の一覧（昇順）。

    59期から「既定期+1」までを基本とし、DB上に存在する期(extra)との和集合を返す。
    """
    base = set(range(CURRENT_FISCAL_PERIOD, default_fiscal_period() + 2))
    if extra:
        base |= {p for p in extra if p is not None}
    return sorted(base)


def month_index(month: str, period: int = CURRENT_FISCAL_PERIOD) -> int | None:
    """その期の中で何番目の月か（0-11）。期外/不正は None。"""
    ms = months(period)
    return ms.index(month) if month in ms else None


# ---- 四半期 ----
# Q番号(1-4) -> その期の中での月インデックス（0-11）
QUARTER_MONTH_INDEXES = {1: [0, 1, 2], 2: [3, 4, 5], 3: [6, 7, 8], 4: [9, 10, 11]}
QUARTER_LABELS = {1: "1Q", 2: "2Q", 3: "3Q", 4: "4Q"}


def quarter_of(month: str, period: int = CURRENT_FISCAL_PERIOD) -> int | None:
    """月 'YYYY-MM' が属するクォーター番号(1-4)。期外/不正は None。"""
    idx = month_index(month, period)
    if idx is None:
        return None
    return idx // 3 + 1


def quarter_months(quarter: int, period: int = CURRENT_FISCAL_PERIOD) -> list[str]:
    """クォーター番号(1-4)に含まれる月リスト。"""
    ms = months(period)
    return [ms[i] for i in QUARTER_MONTH_INDEXES[quarter]]


# ---- 半期 ----
# 1=上期(Q1+Q2), 2=下期(Q3+Q4)
HALF_LABELS = {1: "上期", 2: "下期"}


def half_of(month: str, period: int = CURRENT_FISCAL_PERIOD) -> int | None:
    """月が属する半期(1=上期, 2=下期)。期外/不正は None。"""
    q = quarter_of(month, period)
    if q is None:
        return None
    return 1 if q <= 2 else 2


def half_months(half: int, period: int = CURRENT_FISCAL_PERIOD) -> list[str]:
    """半期(1=上期,2=下期)に含まれる月リスト。"""
    ms = months(period)
    return ms[0:6] if half == 1 else ms[6:12]


def month_label(month: str) -> str:
    """'2026-09' -> '2026/9'（ゼロ埋めなし）。"""
    try:
        y, m = _split(month)
    except (ValueError, TypeError):
        return str(month or "")
    return f"{y}/{m}"


def _split(month: str) -> tuple[int, int]:
    """'YYYY-MM' or 'YYYY/MM' -> (year, month)。不正なら例外。"""
    s = str(month).replace("/", "-")
    y, m = s.split("-")[:2]
    return int(y), int(m)
