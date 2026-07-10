"""案件CRUD・検索・並び替えのテスト。"""
from app.extensions import db
from app.models import Project, Status
from tests.conftest import login


def _create(client, no="P-001", name="テスト案件", **extra):
    data = {"project_no": no, "project_name": name}
    data.update(extra)
    return client.post("/projects/new", data=data, follow_redirects=True)


def test_projects_requires_login(client):
    resp = client.get("/projects", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_create_project(client, app):
    login(client, "admin", "adminpass1")
    resp = _create(client, "P-100", "新規案件A")
    assert resp.status_code == 200
    assert "新規案件A".encode() in resp.data
    with app.app_context():
        p = db.session.get(Project, "P-100")
        assert p is not None
        assert p.created_by == "admin"
        assert p.updated_by == "admin"


def test_duplicate_project_no(client):
    login(client, "admin", "adminpass1")
    _create(client, "P-200", "最初")
    resp = _create(client, "P-200", "重複")
    assert "既に登録されています".encode() in resp.data


def test_project_name_required(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/projects/new",
                       data={"project_no": "P-300", "project_name": ""},
                       follow_redirects=True)
    assert "案件名は必須".encode() in resp.data


def test_invalid_amount(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/projects/new", data={
        "project_no": "P-310", "project_name": "金額不正", "amount_excl_tax": "abc",
    }, follow_redirects=True)
    assert "金額".encode() in resp.data and "数字".encode() in resp.data


def test_invalid_date(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/projects/new", data={
        "project_no": "P-320", "project_name": "日付不正", "order_date": "2020/01/01",
    }, follow_redirects=True)
    assert "YYYY-MM-DD".encode() in resp.data


def test_amount_accepts_comma_and_fullwidth(client, app):
    login(client, "admin", "adminpass1")
    _create(client, "P-330", "金額カンマ", amount_excl_tax="1,234,567")
    with app.app_context():
        assert db.session.get(Project, "P-330").amount_excl_tax == 1234567


def test_search_by_name(client):
    login(client, "admin", "adminpass1")
    _create(client, "P-401", "りんご案件")
    _create(client, "P-402", "みかん案件")
    resp = client.get("/projects?name=りんご")
    assert "りんご案件".encode() in resp.data
    assert "みかん案件".encode() not in resp.data


def test_search_by_status(client, app):
    login(client, "admin", "adminpass1")
    with app.app_context():
        sid = Status.query.filter_by(name="受注").first().id
    _create(client, "P-501", "受注案件", status_id=str(sid))
    _create(client, "P-502", "無ステータス案件")
    resp = client.get(f"/projects?status_id={sid}")
    assert "受注案件".encode() in resp.data
    assert "無ステータス案件".encode() not in resp.data


def test_sort_does_not_error(client):
    login(client, "admin", "adminpass1")
    _create(client, "P-601", "並び替え")
    resp = client.get("/projects?sort=amount_excl_tax&dir=asc")
    assert resp.status_code == 200


def test_edit_project(client, app):
    login(client, "admin", "adminpass1")
    _create(client, "P-700", "編集前")
    resp = client.post("/projects/P-700/edit", data={
        "project_name": "編集後", "customer_name": "顧客X",
    }, follow_redirects=True)
    assert "編集後".encode() in resp.data
    with app.app_context():
        p = db.session.get(Project, "P-700")
        assert p.project_name == "編集後"
        assert p.customer_name == "顧客X"


def test_delete_project(client, app):
    login(client, "admin", "adminpass1")
    _create(client, "P-800", "削除対象")
    resp = client.post("/projects/P-800/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Project, "P-800") is None


def test_detail_404(client):
    login(client, "admin", "adminpass1")
    resp = client.get("/projects/NOPE")
    assert resp.status_code == 404
