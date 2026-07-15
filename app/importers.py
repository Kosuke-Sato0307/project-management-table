"""Excel/CSV からの案件インポート（解析・検証・テンプレ生成）。

59期スキーマ対応。部門スコープで「計上月・担当者・区分・カテゴリー・案件名・確度・
売上・仕入・見込み工数・対応工数・備考」を取り込む。売上総利益は算出のため対象外。

HTTP に依存しないロジックとしてまとめ、単体テストしやすくする。
取込は「全件まとめて成功/失敗」。不正行が1つでもあれば呼び出し側で中止する。
インポート先の期・部門・plan_type は呼び出し側（imports/routes）で付与する。
"""
import csv
import io
from datetime import datetime, date

UNSET = "（未設定）"

# 取込対象の列: (見出し, 属性名, 種別, 必須)
IMPORT_COLUMNS = [
    ("完成月", "accounting_month", "month", True),
    ("担当者", "assignee_user_id", "assignee", False),
    ("区分", "kubun_id", "kubun", False),
    ("カテゴリー", "category_id", "category", False),
    ("案件名", "project_name", "text", True),
    ("取引先", "client_name", "text", False),
    ("エンドユーザ", "end_user_name", "text", False),
    ("商品カテゴリ", "product_category_id", "product_category", False),
    ("確度", "rank_id", "rank", False),
    ("売上", "sales", "int", False),
    ("仕入", "cost", "int", False),
    ("見込み工数", "estimated_hours", "float", False),
    ("対応工数", "actual_hours", "float", False),
    ("備考", "notes", "text", False),
]

# 見出しの表記ゆれを許容
HEADER_ALIASES = {
    "カテゴリ": "カテゴリー",
    "担当": "担当者",
    "計上月": "完成月",
    "エンドユーザー": "エンドユーザ",
    "商品カテゴリー": "商品カテゴリ",
    "売上(円)": "売上",
    "仕入(円)": "仕入",
}

TEMPLATE_HEADERS = [h for h, _, _, _ in IMPORT_COLUMNS]

# ドロップダウン（データ検証）を付ける列 → 選択肢キー
DROPDOWN_HEADERS = {
    "担当者": "assignee",
    "区分": "kubun",
    "カテゴリー": "category",
    "商品カテゴリ": "product_category",
    "確度": "rank",
}


class RowResult:
    """1行の検証結果。"""
    def __init__(self, row_no, data):
        self.row_no = row_no      # ファイル上の行番号（見出し=1）
        self.data = data          # {属性: 値}


# ---------- 値の変換 ----------
def _to_text(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    return str(v).strip()


def _to_int(v):
    """数値化。失敗時は ValueError。"""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, int):
        return v
    if isinstance(v, float):
        if v.is_integer():
            return int(v)
        raise ValueError
    s = str(v).strip().replace(",", "").replace("，", "").translate(
        str.maketrans("０１２３４５６７８９", "0123456789"))
    if s == "":
        return None
    return int(s)  # 失敗すれば ValueError


def _to_float(v):
    """小数化。失敗時は ValueError。"""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("，", "").translate(
        str.maketrans("０１２３４５６７８９．", "0123456789."))
    if s == "":
        return None
    return float(s)  # 失敗すれば ValueError


def _to_month(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m")
    s = str(v).strip().replace("/", "-")
    # 'YYYY-M' も許容して 'YYYY-MM' に正規化
    datetime.strptime(s, "%Y-%m")  # 失敗すれば ValueError
    y, m = s.split("-")[:2]
    return f"{int(y):04d}-{int(m):02d}"


# ---------- ファイル解析 ----------
def _norm_header(h):
    h = "" if h is None else str(h).strip()
    return HEADER_ALIASES.get(h, h)


def parse_file(path, ext):
    """ファイルを (headers, data_rows) に解析する。

    headers: 正規化済みの見出しリスト
    data_rows: [(row_no, [セル値, ...]), ...]（空行は除外、行番号は1始まり）
    CSVは utf-8-sig → cp932 の順で文字コードを試す。
    """
    ext = ext.lower().lstrip(".")
    if ext == "csv":
        raw = open(path, "rb").read()
        text = None
        for enc in ("utf-8-sig", "cp932"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("utf-8", errors="replace")
        all_rows = list(csv.reader(io.StringIO(text)))
    elif ext == "xlsx":
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        all_rows = [list(r) for r in ws.iter_rows(values_only=True)]
        wb.close()
    else:
        raise ValueError("対応していないファイル形式です（.csv / .xlsx のみ）。")

    if not all_rows:
        return [], []

    headers = [_norm_header(h) for h in all_rows[0]]
    data_rows = []
    for i, row in enumerate(all_rows[1:], start=2):
        if all((c is None or str(c).strip() == "") for c in row):
            continue
        data_rows.append((i, list(row)))
    return headers, data_rows


# ---------- 検証 ----------
def validate(headers, data_rows, member_map, kubun_map, category_map, rank_map,
             product_category_map=None):
    """全行を検証する（オールオアナッシング）。

    member_map:           {氏名: user_id}      （その部門のメンバーのみ）
    kubun_map:            {区分名: id}
    category_map:         {コード or 表示名: id} （その部門のカテゴリーのみ）
    rank_map:             {確度名: id}
    product_category_map: {商品カテゴリ名: id}  （その部門のみ）

    戻り値: (results, errors)
      results: list[RowResult]（エラーが無い場合のみ意味を持つ）
      errors:  list[str]（1件でもあれば取込中止）
    """
    product_category_map = product_category_map or {}
    errors = []

    # 見出し→列インデックス
    col_index = {}
    for h, attr, kind, required in IMPORT_COLUMNS:
        if h in headers:
            col_index[attr] = headers.index(h)

    # 必須列（見出し）の存在チェック
    for h, attr, kind, required in IMPORT_COLUMNS:
        if required and attr not in col_index:
            errors.append(f"必須の列「{h}」が見つかりません。テンプレートの見出しをご確認ください。")
    if errors:
        return [], errors

    if not data_rows:
        errors.append("データ行がありません。1行以上入力してください。")
        return [], errors

    lookup = {"assignee": member_map, "kubun": kubun_map,
              "category": category_map, "rank": rank_map,
              "product_category": product_category_map}
    label_of = {attr: h for h, attr, _, _ in IMPORT_COLUMNS}
    results = []

    for row_no, row in data_rows:
        def cell(attr):
            idx = col_index.get(attr)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        data = {}
        row_ok = True

        for _, attr, kind, required in IMPORT_COLUMNS:
            if attr not in col_index:
                data[attr] = None
                continue
            raw = cell(attr)
            try:
                if kind == "text":
                    val = _to_text(raw) or None
                elif kind == "int":
                    val = _to_int(raw)
                elif kind == "float":
                    val = _to_float(raw)
                elif kind == "month":
                    val = _to_month(raw)
                elif kind in ("assignee", "kubun", "category", "rank",
                              "product_category"):
                    name = _to_text(raw) or None
                    if name is None or name == UNSET:
                        val = None
                    elif name in lookup[kind]:
                        val = lookup[kind][name]
                    else:
                        errors.append(
                            f"{row_no}行目: 「{label_of[attr]}」の値『{name}』は"
                            f"この部門に登録がありません。テンプレートの候補から選んでください。")
                        row_ok = False
                        val = None
                else:
                    val = _to_text(raw) or None
            except ValueError:
                errors.append(f"{row_no}行目: 「{label_of[attr]}」の値『{raw}』が正しくありません。")
                row_ok = False
                val = None
            data[attr] = val

        # 必須値
        if not data.get("accounting_month"):
            errors.append(f"{row_no}行目: 完成月が空です（例: 2026-09）。")
            row_ok = False
        if not data.get("project_name"):
            errors.append(f"{row_no}行目: 案件名が空です。")
            row_ok = False

        if row_ok:
            results.append(RowResult(row_no, data))

    return results, errors


# ---------- テンプレート生成 ----------
def template_csv() -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerow(TEMPLATE_HEADERS)
    return buf.getvalue().encode("utf-8-sig")


def template_xlsx(choices=None) -> bytes:
    """Excelテンプレート。

    choices を渡すと 担当者/区分/カテゴリー/確度 列にドロップダウン（データ検証）を付ける。
      choices = {"assignee": [...], "kubun": [...], "category": [...], "rank": [...]}
    金額列は #,##0（カンマ表示）、計上月は @（テキスト）書式にして Excel の自動変換を防ぐ。
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

    choices = choices or {}
    wb = Workbook()
    ws = wb.active
    ws.title = "案件インポート"
    ws.append(TEMPLATE_HEADERS)
    fill = PatternFill("solid", fgColor="2563EB")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = fill
    for i, h in enumerate(TEMPLATE_HEADERS, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(h) * 2 + 2)

    # セル書式: 金額はカンマ、計上月はテキスト（Jul-26化を防ぐ）
    cell_formats = {"int": "#,##0", "month": "@"}
    for idx, (_, _, kind, _) in enumerate(IMPORT_COLUMNS, start=1):
        fmt = cell_formats.get(kind)
        if not fmt:
            continue
        letter = get_column_letter(idx)
        for row in ws[f"{letter}2:{letter}1000"]:
            for cell in row:
                cell.number_format = fmt

    # ドロップダウン（データ検証）を該当列の 2〜1000 行に設定
    for header, key in DROPDOWN_HEADERS.items():
        values = [UNSET] + list(choices.get(key) or [])
        if header not in TEMPLATE_HEADERS or len(values) <= 1:
            continue
        col = get_column_letter(TEMPLATE_HEADERS.index(header) + 1)
        formula = '"' + ",".join(values) + '"'
        # Excel の inline リストは 255 文字まで。超える場合はドロップダウンを付けない。
        if len(formula) > 255:
            continue
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}1000")

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
