"""インポート（Excel/CSV）のテスト。オールオアナッシングを重点検証。"""
import io
import re

from app.extensions import db
from app.models import Project
from tests.conftest import login


def _upload(client, content: bytes, filename="test.csv"):
    return client.post("/import/preview",
                       data={"file": (io.BytesIO(content), filename)},
                       content_type="multipart/form-data",
                       follow_redirects=True)


def _token(resp):
    m = re.search(r'name="token" value="([0-9a-f]{32})"', resp.data.decode())
    return m.group(1) if m else None


def _count(app):
    with app.app_context():
        return Project.query.count()


def test_templates_download(client):
    login(client, "admin", "adminpass1")
    assert client.get("/import/template.csv").status_code == 200
    xlsx = client.get("/import/template.xlsx")
    assert xlsx.status_code == 200
    assert "spreadsheetml" in xlsx.headers["Content-Type"]


def test_import_valid_csv(client, app):
    login(client, "admin", "adminpass1")
    csv = "案件番号,案件名,金額(税抜)\nIMP-1,インポート案件,1000000\n".encode("utf-8-sig")
    resp = _upload(client, csv)
    assert "取り込み対象".encode() in resp.data
    token = _token(resp)
    assert token
    resp2 = client.post("/import/commit", data={"token": token, "dup_mode": "skip"},
                        follow_redirects=True)
    assert "インポート完了".encode() in resp2.data
    with app.app_context():
        p = db.session.get(Project, "IMP-1")
        assert p is not None
        assert p.project_name == "インポート案件"
        assert p.amount_excl_tax == 1000000
        assert p.created_by == "admin"


def test_import_all_or_nothing_on_error(client, app):
    login(client, "admin", "adminpass1")
    before = _count(app)
    # 2行目は正常、3行目は案件名が空（エラー）
    csv = "案件番号,案件名\nOK-1,正常案件\nNG-1,\n".encode("utf-8-sig")
    resp = _upload(client, csv)
    assert "取り込めませんでした".encode() in resp.data
    assert "案件名が空".encode() in resp.data
    # 1件も取り込まれていないこと
    assert _count(app) == before
    with app.app_context():
        assert db.session.get(Project, "OK-1") is None


def test_import_invalid_amount_blocks_all(client, app):
    login(client, "admin", "adminpass1")
    before = _count(app)
    csv = "案件番号,案件名,金額(税抜)\nA-1,案件A,100\nB-1,案件B,abc\n".encode("utf-8-sig")
    resp = _upload(client, csv)
    assert "取り込めませんでした".encode() in resp.data
    assert _count(app) == before


def test_import_unknown_status_blocks(client, app):
    login(client, "admin", "adminpass1")
    before = _count(app)
    csv = "案件番号,案件名,ステータス\nS-1,案件,存在しない状態\n".encode("utf-8-sig")
    resp = _upload(client, csv)
    assert "未登録".encode() in resp.data
    assert _count(app) == before


def test_import_in_file_duplicate_blocks(client, app):
    login(client, "admin", "adminpass1")
    before = _count(app)
    csv = "案件番号,案件名\nD-1,案件1\nD-1,案件2\n".encode("utf-8-sig")
    resp = _upload(client, csv)
    assert "重複".encode() in resp.data
    assert _count(app) == before


def test_import_duplicate_skip_and_overwrite(client, app):
    login(client, "admin", "adminpass1")
    # 既存案件を作成
    client.post("/projects/new", data={"project_no": "DUP-1", "project_name": "元の名前"},
                follow_redirects=True)

    csv = "案件番号,案件名\nDUP-1,新しい名前\n".encode("utf-8-sig")

    # スキップ → 変わらない
    resp = _upload(client, csv)
    token = _token(resp)
    client.post("/import/commit", data={"token": token, "dup_mode": "skip"}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Project, "DUP-1").project_name == "元の名前"

    # 上書き → 更新される
    resp = _upload(client, csv)
    token = _token(resp)
    client.post("/import/commit", data={"token": token, "dup_mode": "overwrite"}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Project, "DUP-1").project_name == "新しい名前"


def test_import_cp932_csv(client, app):
    login(client, "admin", "adminpass1")
    csv = "案件番号,案件名\nCP-1,シフトジス案件\n".encode("cp932")
    resp = _upload(client, csv)
    token = _token(resp)
    assert token
    client.post("/import/commit", data={"token": token, "dup_mode": "skip"}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Project, "CP-1").project_name == "シフトジス案件"


def test_import_xlsx_with_date_and_status(client, app):
    """Excel経路：日付セル・ステータス名の解決・金額数値を検証。"""
    import datetime
    from openpyxl import Workbook

    login(client, "admin", "adminpass1")
    wb = Workbook()
    ws = wb.active
    ws.append(["案件番号", "案件名", "ステータス", "確度", "金額(税抜)", "完成月", "受注日"])
    ws.append(["XL-1", "エクセル案件", "進行中", "A", 2500000, "2026-10",
               datetime.date(2026, 7, 5)])
    bio = io.BytesIO()
    wb.save(bio)

    resp = _upload(client, bio.getvalue(), filename="in.xlsx")
    assert "取り込み対象".encode() in resp.data
    token = _token(resp)
    client.post("/import/commit", data={"token": token, "dup_mode": "skip"},
                follow_redirects=True)
    with app.app_context():
        from app.models import Status, Rank
        p = db.session.get(Project, "XL-1")
        assert p is not None
        assert p.amount_excl_tax == 2500000
        assert p.completion_month == "2026-10"
        assert p.order_date == datetime.date(2026, 7, 5)
        assert p.status_id == Status.query.filter_by(name="進行中").first().id
        assert p.rank_id == Rank.query.filter_by(name="A").first().id


def test_import_requires_file(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/import/preview", data={}, content_type="multipart/form-data",
                       follow_redirects=True)
    assert "ファイルを選択".encode() in resp.data
