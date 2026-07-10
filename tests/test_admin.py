"""管理者のユーザー管理テスト。"""
from app.extensions import db
from app.models import User
from tests.conftest import login


def test_non_admin_cannot_access_user_admin(client):
    login(client, "taro", "initpass12")
    resp = client.get("/admin/users")
    # 一般ユーザーは 403（初回PW変更前でもガードで弾かれる場合はリダイレクト）
    assert resp.status_code in (302, 403)


def test_admin_can_list_users(client):
    login(client, "admin", "adminpass1")
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert "山田太郎".encode() in resp.data


def test_admin_can_create_user(client, app):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/users/new", data={
        "user_id": "hanako", "name": "鈴木花子", "role": "user",
    }, follow_redirects=True)
    assert resp.status_code == 200
    # 初期パスワードが画面に一度だけ表示される
    assert "初期パスワード".encode() in resp.data
    with app.app_context():
        u = db.session.get(User, "hanako")
        assert u is not None
        assert u.must_change_password is True


def test_create_user_duplicate_id(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/users/new", data={
        "user_id": "taro", "name": "重複", "role": "user",
    })
    assert "既に使われています".encode() in resp.data


def test_reset_password(client, app):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/users/taro/reset-password", follow_redirects=True)
    assert resp.status_code == 200
    assert "初期パスワード".encode() in resp.data
    with app.app_context():
        assert db.session.get(User, "taro").must_change_password is True


def test_cannot_disable_self(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/users/admin/toggle-active", follow_redirects=True)
    assert "自分自身は無効化できません".encode() in resp.data


def test_cannot_demote_last_admin(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/users/admin/role",
                       data={"role": "user"}, follow_redirects=True)
    assert "管理者が1人だけ".encode() in resp.data
