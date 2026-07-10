"""認証まわりのテスト。"""
from app.extensions import db
from app.models import User
from tests.conftest import login


def test_login_page_accessible(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "ログイン".encode() in resp.data


def test_protected_page_redirects_to_login(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_success(client):
    resp = login(client, "admin", "adminpass1")
    assert resp.status_code == 200
    assert "ホーム".encode() in resp.data


def test_login_wrong_password(client):
    resp = client.post("/login", data={"user_id": "admin", "password": "wrong"})
    assert resp.status_code == 401
    assert "違います".encode() in resp.data


def test_inactive_user_cannot_login(client, app):
    with app.app_context():
        u = db.session.get(User, "taro")
        u.is_active_flag = False
        db.session.commit()
    resp = client.post("/login", data={"user_id": "taro", "password": "initpass12"})
    assert resp.status_code == 403


def test_first_login_forces_password_change(client):
    # must_change_password=True のユーザーはPW変更画面へ誘導される
    resp = login(client, "taro", "initpass12")
    assert resp.status_code == 200
    assert "パスワード変更".encode() in resp.data


def test_change_password_flow(client, app):
    login(client, "taro", "initpass12")
    resp = client.post("/change-password", data={
        "current_password": "initpass12",
        "new_password": "brandnew99",
        "new_password_confirm": "brandnew99",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        u = db.session.get(User, "taro")
        assert u.must_change_password is False
        assert u.check_password("brandnew99")


def test_change_password_mismatch(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/change-password", data={
        "current_password": "adminpass1",
        "new_password": "brandnew99",
        "new_password_confirm": "different99",
    })
    assert "一致しません".encode() in resp.data
