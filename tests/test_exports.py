"""エクスポート（CSV/Excel/PDF）のテスト。"""
import io

from openpyxl import load_workbook
from tests.conftest import login


def _create(client, no, name, **extra):
    data = {"project_no": no, "project_name": name}
    data.update(extra)
    return client.post("/projects/new", data=data, follow_redirects=True)


def test_export_csv(client):
    login(client, "admin", "adminpass1")
    _create(client, "E-001", "エクスポート案件", amount_excl_tax="1000000")
    resp = client.get("/projects/export.csv")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["Content-Type"]
    # BOM付きUTF-8で日本語が化けずに読める
    text = resp.data.decode("utf-8-sig")
    assert "案件番号" in text          # ヘッダー
    assert "エクスポート案件" in text  # データ
    assert "1,000,000" in text         # 金額はカンマ表示


def test_export_xlsx(client):
    login(client, "admin", "adminpass1")
    _create(client, "E-101", "エクセル案件", amount_excl_tax="500000")
    resp = client.get("/projects/export.xlsx")
    assert resp.status_code == 200
    assert "spreadsheetml" in resp.headers["Content-Type"]
    wb = load_workbook(io.BytesIO(resp.data))
    ws = wb.active
    assert ws.cell(row=1, column=1).value == "案件番号"
    # データ行に案件名が含まれる
    values = [c.value for row in ws.iter_rows(min_row=2) for c in row]
    assert "エクセル案件" in values
    assert 500000 in values  # 金額は数値として格納


def test_export_pdf(client):
    login(client, "admin", "adminpass1")
    _create(client, "E-201", "PDF案件")
    resp = client.get("/projects/export.pdf")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"] == "application/pdf"
    assert resp.data[:4] == b"%PDF"
    assert len(resp.data) > 1000


def test_export_respects_filter(client):
    login(client, "admin", "adminpass1")
    _create(client, "E-301", "りんごエクスポート")
    _create(client, "E-302", "みかんエクスポート")
    text = client.get("/projects/export.csv?name=りんご").data.decode("utf-8-sig")
    assert "りんごエクスポート" in text
    assert "みかんエクスポート" not in text


def test_export_requires_login(client):
    resp = client.get("/projects/export.csv", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]
