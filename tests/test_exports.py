"""エクスポート（CSV/Excel/PDF）のテスト（新スキーマ）。"""
import io

from openpyxl import load_workbook
from tests.conftest import login


def test_export_csv(client):
    login(client, "admin", "adminpass1")
    resp = client.get("/projects/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["Content-Type"]
    text = resp.data.decode("utf-8-sig")
    assert "計上月" in text          # 新ヘッダー
    assert "担当者" in text
    assert "売上総利益" in text
    assert "計画案件A" in text       # conftest のデータ
    assert "1,000,000" in text       # 売上はカンマ表示


def test_export_xlsx(client):
    login(client, "admin", "adminpass1")
    resp = client.get("/projects/export.xlsx")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["Content-Type"]
    wb = load_workbook(io.BytesIO(resp.data))
    ws = wb.active
    assert ws.cell(row=1, column=1).value == "計上月"
    values = [c.value for row in ws.iter_rows(min_row=2) for c in row]
    assert "計画案件A" in values
    assert 1000000 in values         # 売上は数値として格納


def test_export_pdf(client):
    login(client, "admin", "adminpass1")
    resp = client.get("/projects/export.pdf")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert resp.data[:4] == b"%PDF"
    assert len(resp.data) > 1000


def test_export_requires_login(client):
    resp = client.get("/projects/export.csv", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
