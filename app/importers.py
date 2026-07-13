"""Excel/CSV からの案件インポート（解析・検証・テンプレ生成）。

HTTP に依存しないロジックとしてまとめ、単体テストしやすくする。
取込は「全件まとめて成功/失敗」。不正行が1つでもあれば呼び出し側で中止する。
"""
import csv
import io
from datetime import datetime, date

# 取込対象の列（監査列は対象外）: (見出し, 属性名, 種別, 必須)
IMPORT_COLUMNS = [
    ("案件番号", "project_no", "text", True),
    ("案件名", "project_name", "text", True),
    ("顧客名", "customer_name", "text", False),
    ("ステータス", "status_id", "status", False),
    ("確度", "rank_id", "rank", False),
    ("見積番号", "estimate_no", "text", False),
    ("金額(税抜)", "amount_excl_tax", "int", False),
    ("完成月", "completion_month", "month", False),
    ("受注日", "order_date", "date", False),
    ("営業担当者", "sales_rep", "text", False),
    ("部署", "department", "department", False),
    ("備考メモ", "notes", "text", False),
]

# 「（未設定）」は空（None）として扱う
UNSET = "（未設定）"

# 見出しの表記ゆれを許容
HEADER_ALIASES = {
    "顧客名/取引先": "顧客名",
    "取引先": "顧客名",
    "金額（税抜）": "金額(税抜)",
    "金額": "金額(税抜)",
}

TEMPLATE_HEADERS = [h for h, _, _, _ in IMPORT_COLUMNS]


class RowResult:
    """1行の検証結果。"""
    def __init__(self, row_no, data, action):
        self.row_no = row_no      # ファイル上の行番号（見出し=1）
        self.data = data          # {属性: 値}
        self.action = action      # "new" or "update"


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


def _to_date(v):
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError


def _to_month(v):
    """完成月を 'YYYY-MM'（ゼロ埋め）に正規化。"""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m")
    s = str(v).strip().replace("/", "-")
    return datetime.strptime(s, "%Y-%m").strftime("%Y-%m")  # 失敗すれば ValueError


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
def validate(headers, data_rows, existing_nos, status_map, rank_map, dept_map=None):
    """全行を検証する。

    戻り値: (results, errors)
      results: list[RowResult]（エラーが無い場合のみ意味を持つ）
      errors:  list[str]（1件でもあれば取込中止）
    """
    dept_names = set(dept_map or [])
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

    kind_map = {attr: kind for _, attr, kind, _ in IMPORT_COLUMNS}
    results = []
    seen_nos = {}

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
                elif kind == "date":
                    val = _to_date(raw)
                elif kind == "month":
                    val = _to_month(raw)
                elif kind == "status":
                    name = _to_text(raw) or None
                    if name is None or name == UNSET:
                        val = None
                    elif name in status_map:
                        val = status_map[name]
                    else:
                        errors.append(f"{row_no}行目: ステータス「{name}」は未登録です。マスタに追加してください。")
                        row_ok = False
                        val = None
                elif kind == "rank":
                    name = _to_text(raw) or None
                    if name is None or name == UNSET:
                        val = None
                    elif name in rank_map:
                        val = rank_map[name]
                    else:
                        errors.append(f"{row_no}行目: 確度「{name}」は未登録です。マスタに追加してください。")
                        row_ok = False
                        val = None
                elif kind == "department":
                    name = _to_text(raw) or None
                    if name is None or name == UNSET:
                        val = None
                    elif name in dept_names:
                        val = name  # 部署は名称を保存
                    else:
                        errors.append(f"{row_no}行目: 部署「{name}」は未登録です。マスタに追加してください。")
                        row_ok = False
                        val = None
                else:
                    val = _to_text(raw) or None
            except ValueError:
                label = next(h for h, a, _, _ in IMPORT_COLUMNS if a == attr)
                errors.append(f"{row_no}行目: 「{label}」の値『{raw}』が正しくありません。")
                row_ok = False
                val = None
            data[attr] = val

        # 必須値
        if not data.get("project_no"):
            errors.append(f"{row_no}行目: 案件番号が空です。")
            row_ok = False
        if not data.get("project_name"):
            errors.append(f"{row_no}行目: 案件名が空です。")
            row_ok = False

        # ファイル内での案件番号重複
        no = data.get("project_no")
        if no:
            if no in seen_nos:
                errors.append(f"{row_no}行目: 案件番号『{no}』がファイル内で重複しています（{seen_nos[no]}行目と重複）。")
                row_ok = False
            else:
                seen_nos[no] = row_no

        if row_ok:
            action = "update" if no in existing_nos else "new"
            results.append(RowResult(row_no, data, action))

    return results, errors


# ---------- テンプレート生成 ----------
def template_csv() -> bytes:
    buf = io.StringIO()
    csv.writer(buf).writerow(TEMPLATE_HEADERS)
    return buf.getvalue().encode("utf-8-sig")


def template_xlsx(status_names=None, rank_names=None, dept_names=None) -> bytes:
    """Excelテンプレート。ステータス/確度/部署の列はドロップダウンにする。"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter
    from openpyxl.worksheet.datavalidation import DataValidation

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

    # 入力時の表示崩れを防ぐため、列ごとにセル書式（number_format）を 2〜1000 行へ設定する。
    #   金額(税抜): #,##0 → 500000 を 500,000 と桁区切り表示
    #   完成月    : @（テキスト）→ 2026/7 が Excel で Jul-26 に自動変換されるのを防ぐ
    cell_formats = {"int": "#,##0", "month": "@"}
    for idx, (_, _, kind, _) in enumerate(IMPORT_COLUMNS, start=1):
        fmt = cell_formats.get(kind)
        if not fmt:
            continue
        letter = get_column_letter(idx)
        for row in ws[f"{letter}2:{letter}1000"]:
            for cell in row:
                cell.number_format = fmt

    # ドロップダウン（データ入力規則）を該当列の 2〜1000 行に設定
    choices = {
        "ステータス": [UNSET] + list(status_names or []),
        "確度": [UNSET] + list(rank_names or []),
        "部署": [UNSET] + list(dept_names or []),
    }
    for header, values in choices.items():
        if header not in TEMPLATE_HEADERS or len(values) <= 1:
            continue
        col = get_column_letter(TEMPLATE_HEADERS.index(header) + 1)
        formula = '"' + ",".join(values) + '"'
        dv = DataValidation(type="list", formula1=formula, allow_blank=True)
        ws.add_data_validation(dv)
        dv.add(f"{col}2:{col}1000")

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()
