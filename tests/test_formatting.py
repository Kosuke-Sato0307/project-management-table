"""フェーズ5: 表示・入力書式（日付yyyy/m/d・完成月yyyy/m・金額カンマ・部署）のテスト。"""
import datetime

from app.extensions import db
from app.models import Project
from tests.conftest import login


def test_form_accepts_slash_date_and_month(client, app):
    login(client, "admin", "adminpass1")
    resp = client.post("/projects/new", data={
        "project_no": "F-1", "project_name": "書式テスト",
        "amount_excl_tax": "1,000,000",
        "completion_month": "2026/7",
        "order_date": "2026/7/5",
        "department": "第1営業部",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        p = db.session.get(Project, "F-1")
        assert p.amount_excl_tax == 1000000          # カンマ除去
        assert p.completion_month == "2026-07"        # 正規化保存
        assert p.order_date == datetime.date(2026, 7, 5)
        assert p.department == "第1営業部"


def test_detail_shows_slash_formats(client):
    login(client, "admin", "adminpass1")
    client.post("/projects/new", data={
        "project_no": "F-2", "project_name": "表示テスト",
        "amount_excl_tax": "2500000", "completion_month": "2026/9",
        "order_date": "2026/7/5",
    }, follow_redirects=True)
    html = client.get("/projects/F-2").data.decode()
    assert "2026/9" in html          # 完成月 yyyy/m
    assert "2026/7/5" in html        # 日付 yyyy/m/d
    assert "2,500,000" in html       # 金額カンマ


def test_invalid_date_format_rejected(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/projects/new", data={
        "project_no": "F-3", "project_name": "不正日付", "order_date": "2026.7.5",
    }, follow_redirects=True)
    assert "2026/7/5 の形式".encode() in resp.data


def test_month_range_search_with_slash(client):
    login(client, "admin", "adminpass1")
    client.post("/projects/new", data={"project_no": "M-1", "project_name": "7月案件",
                                        "completion_month": "2026/7"}, follow_redirects=True)
    client.post("/projects/new", data={"project_no": "M-2", "project_name": "12月案件",
                                        "completion_month": "2026/12"}, follow_redirects=True)
    # 2026/8〜2026/12 の範囲で検索 → 12月案件のみ
    resp = client.get("/projects?month_from=2026/8&month_to=2026/12")
    assert "12月案件".encode() in resp.data
    assert "7月案件".encode() not in resp.data


def test_export_csv_date_month_format(client):
    login(client, "admin", "adminpass1")
    client.post("/projects/new", data={
        "project_no": "E-9", "project_name": "書式出力", "completion_month": "2026/7",
        "order_date": "2026/7/5", "amount_excl_tax": "1234567",
    }, follow_redirects=True)
    text = client.get("/projects/export.csv?no=E-9").data.decode("utf-8-sig")
    assert "2026/7" in text        # 完成月
    assert "2026/7/5" in text      # 受注日
    assert "1,234,567" in text     # 金額カンマ


def test_import_department_validation(client, app):
    login(client, "admin", "adminpass1")
    # 既知の部署はOK
    import io
    csv_ok = "案件番号,案件名,部署\nD-OK,部署あり,第1営業部\n".encode("utf-8-sig")
    resp = client.post("/import/preview",
                       data={"file": (io.BytesIO(csv_ok), "d.csv")},
                       content_type="multipart/form-data", follow_redirects=True)
    import re
    token = re.search(r'name="token" value="([0-9a-f]{32})"', resp.data.decode()).group(1)
    client.post("/import/commit", data={"token": token, "dup_mode": "skip"},
                follow_redirects=True)
    with app.app_context():
        assert db.session.get(Project, "D-OK").department == "第1営業部"


def test_import_unknown_department_blocks(client, app):
    login(client, "admin", "adminpass1")
    before = Project.query.count() if False else None
    import io
    csv_ng = "案件番号,案件名,部署\nD-NG,部署不正,存在しない部署\n".encode("utf-8-sig")
    resp = client.post("/import/preview",
                       data={"file": (io.BytesIO(csv_ng), "d.csv")},
                       content_type="multipart/form-data", follow_redirects=True)
    assert "未登録".encode() in resp.data
    with app.app_context():
        assert db.session.get(Project, "D-NG") is None


def test_import_unset_becomes_none(client, app):
    login(client, "admin", "adminpass1")
    import io
    csv = "案件番号,案件名,ステータス,部署\nU-1,未設定テスト,（未設定）,（未設定）\n".encode("utf-8-sig")
    resp = client.post("/import/preview",
                       data={"file": (io.BytesIO(csv), "u.csv")},
                       content_type="multipart/form-data", follow_redirects=True)
    import re
    token = re.search(r'name="token" value="([0-9a-f]{32})"', resp.data.decode()).group(1)
    client.post("/import/commit", data={"token": token, "dup_mode": "skip"},
                follow_redirects=True)
    with app.app_context():
        p = db.session.get(Project, "U-1")
        assert p.status_id is None
        assert p.department is None
