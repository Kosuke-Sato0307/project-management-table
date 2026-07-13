"""案件データの CSV / Excel / PDF 出力。

列定義（COLUMNS）を1箇所に集約し、各形式で共用する。
PDFの日本語表示は、同梱フォント(ipaexg.ttf)を埋め込む。無ければ reportlab
内蔵の日本語CIDフォントに自動フォールバックする（開発時などフォント未取得でも生成可）。
"""
import csv
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))


def _d(value):
    """日付 → 'YYYY-MM-DD'（Noneは空文字）。"""
    return value.strftime("%Y-%m-%d") if value else ""


def _dt(value):
    """日時(UTC保存) → JSTの 'YYYY-MM-DD HH:MM'。"""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(JST).strftime("%Y-%m-%d %H:%M")


# 列定義: (見出し, 値を取り出す関数)。金額は数値のまま（Excelで集計できるように）。
COLUMNS = [
    ("案件番号", lambda p: p.project_no),
    ("案件名", lambda p: p.project_name),
    ("顧客名", lambda p: p.customer_name or ""),
    ("ステータス", lambda p: p.status.name if p.status else ""),
    ("確度", lambda p: p.rank.name if p.rank else ""),
    ("見積番号", lambda p: p.estimate_no or ""),
    ("金額(税抜)", lambda p: p.amount_excl_tax),
    ("完成月", lambda p: p.completion_month or ""),
    ("受注日", lambda p: _d(p.order_date)),
    ("保守開始日", lambda p: _d(p.maintenance_start)),
    ("保守終了日", lambda p: _d(p.maintenance_end)),
    ("営業担当者", lambda p: p.sales_rep or ""),
    ("部署", lambda p: p.department or ""),
    ("備考メモ", lambda p: p.notes or ""),
    ("作成日時", lambda p: _dt(p.created_at)),
    ("作成者", lambda p: p.created_by or ""),
    ("編集日時", lambda p: _dt(p.updated_at)),
    ("編集者", lambda p: p.updated_by or ""),
]

# PDFは読みやすさ優先で主要列のみ
PDF_COLUMNS = ["案件番号", "案件名", "顧客名", "ステータス", "確度", "金額(税抜)", "完成月"]


# ---------- CSV ----------
def to_csv(projects) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([h for h, _ in COLUMNS])
    for p in projects:
        writer.writerow([acc(p) for _, acc in COLUMNS])
    # Excelで開いたとき日本語が化けないよう BOM 付き UTF-8
    return buf.getvalue().encode("utf-8-sig")


# ---------- Excel ----------
def to_xlsx(projects) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    ws = wb.active
    ws.title = "案件一覧"

    headers = [h for h, _ in COLUMNS]
    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="2563EB")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center")

    for p in projects:
        ws.append([acc(p) for _, acc in COLUMNS])

    ws.freeze_panes = "A2"
    for i, (h, _) in enumerate(COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = max(12, len(h) * 2 + 2)

    # 金額列を桁区切り書式に
    amount_idx = next(i for i, (h, _) in enumerate(COLUMNS, 1) if h == "金額(税抜)")
    for row in ws.iter_rows(min_row=2, min_col=amount_idx, max_col=amount_idx):
        for cell in row:
            cell.number_format = "#,##0"

    bio = io.BytesIO()
    wb.save(bio)
    return bio.getvalue()


# ---------- PDF ----------
_pdf_font_name = None


def _register_pdf_font() -> str:
    """PDF用日本語フォントを登録し、フォント名を返す（初回のみ登録）。"""
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
        # 同梱フォントが無い場合は内蔵の日本語CIDフォントにフォールバック
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
    jp = ParagraphStyle("jp", parent=styles["Normal"], fontName=font,
                        fontSize=8, leading=11)
    jp_head = ParagraphStyle("jph", parent=jp, textColor=colors.white)
    title_style = ParagraphStyle("t", parent=styles["Title"], fontName=font, fontSize=14)
    small = ParagraphStyle("s", parent=jp, fontSize=8, textColor=colors.grey)

    bio = io.BytesIO()
    doc = SimpleDocTemplate(bio, pagesize=landscape(A4),
                            leftMargin=10 * mm, rightMargin=10 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)

    acc_map = {h: acc for h, acc in COLUMNS}
    header = [Paragraph(h, jp_head) for h in PDF_COLUMNS]
    data = [header]
    for p in projects:
        row = []
        for h in PDF_COLUMNS:
            v = acc_map[h](p)
            if h == "金額(税抜)":
                v = "" if v is None else f"{v:,}"
            row.append(Paragraph("" if v is None else str(v), jp))
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
        Paragraph(f"出力日時: {_dt(datetime.now(timezone.utc))}　件数: {len(projects)}", small),
        Spacer(1, 6),
        table,
    ]
    doc.build(elems)
    return bio.getvalue()
