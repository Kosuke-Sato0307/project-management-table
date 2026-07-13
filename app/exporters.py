"""案件データの CSV / Excel / PDF 出力。

列定義（COLUMNS）を1箇所に集約し、形式ごとに適切に整形する。
  - 金額: CSV/PDFはカンマ文字列、Excelは数値+桁区切り書式（合計可）
  - 日付: yyyy/m/d、完成月: yyyy/m（ExcelでもJul-26化しないよう文字列/書式で制御）
PDFの日本語は同梱フォント(ipaexg.ttf)を埋め込む（無ければ内蔵CIDフォントに自動フォールバック）。
"""
import csv
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))

# (見出し, 属性, 種別)
COLUMNS = [
    ("案件番号", "project_no", "text"),
    ("案件名", "project_name", "text"),
    ("顧客名", "customer_name", "text"),
    ("ステータス", "status", "status"),
    ("確度", "rank", "rank"),
    ("見積番号", "estimate_no", "text"),
    ("金額(税抜)", "amount_excl_tax", "int"),
    ("完成月", "completion_month", "month"),
    ("受注日", "order_date", "date"),
    ("営業担当者", "sales_rep", "text"),
    ("部署", "department", "text"),
    ("備考メモ", "notes", "text"),
    ("作成日時", "created_at", "datetime"),
    ("作成者", "created_by", "text"),
    ("編集日時", "updated_at", "datetime"),
    ("編集者", "updated_by", "text"),
]

PDF_COLUMNS = ["案件番号", "案件名", "顧客名", "ステータス", "確度", "金額(税抜)", "完成月"]


# ---------- 値の取り出し・整形 ----------
def _raw(p, attr, kind):
    if kind == "status":
        return p.status.name if p.status else None
    if kind == "rank":
        return p.rank.name if p.rank else None
    return getattr(p, attr)


def _fmt_ymd(d):
    return f"{d.year}/{d.month}/{d.day}" if d else ""


def _fmt_month(s):
    if not s:
        return ""
    parts = str(s).replace("/", "-").split("-")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        return f"{int(parts[0])}/{int(parts[1])}"
    return str(s)


def _fmt_dt(v):
    if v is None:
        return ""
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    v = v.astimezone(JST)
    return f"{v.year}/{v.month}/{v.day} {v.strftime('%H:%M')}"


def _text_value(p, attr, kind):
    """CSV/PDF用: すべて文字列に整形。"""
    v = _raw(p, attr, kind)
    if kind == "int":
        return "" if v is None else f"{v:,}"
    if kind == "date":
        return _fmt_ymd(v)
    if kind == "month":
        return _fmt_month(v)
    if kind == "datetime":
        return _fmt_dt(v)
    return "" if v is None else str(v)


# ---------- CSV ----------
def to_csv(projects) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([h for h, _, _ in COLUMNS])
    for p in projects:
        writer.writerow([_text_value(p, attr, kind) for _, attr, kind in COLUMNS])
    return buf.getvalue().encode("utf-8-sig")


# ---------- Excel ----------
def to_xlsx(projects) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "案件一覧"

    ws.append([h for h, _, _ in COLUMNS])
    header_fill = PatternFill("solid", fgColor="2563EB")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

    for p in projects:
        row = []
        for _, attr, kind in COLUMNS:
            v = _raw(p, attr, kind)
            if kind == "int":
                row.append(v)                       # 数値のまま
            elif kind == "date":
                row.append(v)                       # 実日付
            elif kind == "month":
                row.append(_fmt_month(v))           # 文字列 yyyy/m
            elif kind == "datetime":
                row.append(_fmt_dt(v))              # 文字列
            else:
                row.append("" if v is None else str(v))
        ws.append(row)

    ws.freeze_panes = "A2"
    for i, (h, _, kind) in enumerate(COLUMNS, start=1):
        letter = get_column_letter(i)
        ws.column_dimensions[letter].width = max(12, len(h) * 2 + 2)
        if kind in ("int", "date", "month"):
            fmt = {"int": "#,##0", "date": "yyyy/m/d", "month": "@"}[kind]
            for row in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                for cell in row:
                    cell.number_format = fmt

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ---------- PDF ----------
_pdf_font_name = None


def _register_pdf_font() -> str:
    global _pdf_font_name
    if _pdf_font_name:
        return _pdf_font_name

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    font_path = Path(__file__).resolve().parent / "static" / "fonts" / "ipaexg.ttf"
    try:
        if font_path.exists():
            pdfmetrics.registerFont(TTFont("IPAexGothic", str(font_path)))
            _pdf_font_name = "IPAexGothic"
        else:
            raise FileNotFoundError
    except Exception:
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        _pdf_font_name = "HeiseiKakuGo-W5"
    return _pdf_font_name


def to_pdf(projects, title="案件一覧") -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer)

    font = _register_pdf_font()
    styles = getSampleStyleSheet()
    jp = ParagraphStyle("jp", parent=styles["Normal"], fontName=font, fontSize=8, leading=11)
    jp_head = ParagraphStyle("jph", parent=jp, textColor=colors.white)
    title_style = ParagraphStyle("t", parent=styles["Title"], fontName=font, fontSize=14)
    small = ParagraphStyle("s", parent=jp, fontSize=8, textColor=colors.grey)

    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4),
                            leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)

    col_def = {h: (attr, kind) for h, attr, kind in COLUMNS}
    header = [Paragraph(h, jp_head) for h in PDF_COLUMNS]
    data = [header]
    for p in projects:
        row = []
        for h in PDF_COLUMNS:
            attr, kind = col_def[h]
            row.append(Paragraph(_text_value(p, attr, kind), jp))
        data.append(row)

    total_w = 277 * mm
    weights = {"案件番号": 1.1, "案件名": 2.4, "顧客名": 1.8, "ステータス": 1.0,
               "確度": 0.7, "金額(税抜)": 1.2, "完成月": 0.9}
    wsum = sum(weights[h] for h in PDF_COLUMNS)
    col_widths = [total_w * weights[h] / wsum for h in PDF_COLUMNS]
    amount_col = PDF_COLUMNS.index("金額(税抜)")

    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2563EB")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f7fa")]),
        ("ALIGN", (amount_col, 1), (amount_col, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    elems = [
        Paragraph(title, title_style),
        Paragraph(f"出力日時: {_fmt_dt(datetime.now(timezone.utc))}　件数: {len(projects)}", small),
        Spacer(1, 6),
        table,
    ]
    doc.build(elems)
    return bio.getvalue()
