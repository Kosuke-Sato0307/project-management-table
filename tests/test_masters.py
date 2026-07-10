"""マスタ管理（ステータス・確度ランク）のテスト。"""
from app.extensions import db
from app.models import Status, Rank
from tests.conftest import login


def test_non_admin_cannot_access_masters(client):
    login(client, "taro", "initpass12")
    assert client.get("/admin/statuses").status_code == 403
    assert client.get("/admin/ranks").status_code == 403


def test_admin_add_status(client, app):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/statuses/new",
                       data={"name": "保留", "sort_order": "5"},
                       follow_redirects=True)
    assert "追加しました".encode() in resp.data
    with app.app_context():
        assert Status.query.filter_by(name="保留").first() is not None


def test_add_duplicate_status(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/statuses/new",
                       data={"name": "受注", "sort_order": "0"},
                       follow_redirects=True)
    assert "既に存在します".encode() in resp.data


def test_edit_status(client, app):
    login(client, "admin", "adminpass1")
    with app.app_context():
        sid = Status.query.filter_by(name="進行中").first().id
    client.post(f"/admin/statuses/{sid}/edit",
                data={"name": "対応中", "sort_order": "1"}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Status, sid).name == "対応中"


def test_toggle_status_hides_from_active(client, app):
    login(client, "admin", "adminpass1")
    with app.app_context():
        sid = Status.query.filter_by(name="進行中").first().id
    client.post(f"/admin/statuses/{sid}/toggle", follow_redirects=True)
    with app.app_context():
        assert db.session.get(Status, sid).is_active is False


def test_admin_add_rank(client, app):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/ranks/new",
                       data={"name": "S", "note": "最優先", "sort_order": "0"},
                       follow_redirects=True)
    assert "追加しました".encode() in resp.data
    with app.app_context():
        r = Rank.query.filter_by(name="S").first()
        assert r is not None and r.note == "最優先"
