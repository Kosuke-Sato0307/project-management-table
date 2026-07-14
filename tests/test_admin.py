"""システム管理者のユーザー管理テスト。"""
from app.extensions import db
from app.models import User
from tests.conftest import login


def test_general_user_cannot_access_user_admin(client):
    login(client, "hanako", "hanakopass1")
    resp = client.get("/admin/users")
    assert resp.status_code == 403


def test_manager_cannot_access_user_admin(client):
    # 管理者（部門長）はユーザー管理不可（sysadmin専用）
    login(client, "bucho", "buchopass1")
    resp = client.get("/admin/users")
    assert resp.status_code == 403


def test_sysadmin_can_list_users(client):
    login(client, "admin", "adminpass1")
    resp = client.get("/admin/users")
    assert resp.status_code == 200
    assert "山田太郎".encode() in resp.data


def test_sysadmin_can_create_user_with_departments(client, app):
    login(client, "admin", "adminpass1")
    with app.app_context():
        from app.models import Department
        dept2_id = Department.query.filter_by(name="第2営業部").first().id
    resp = client.post("/admin/users/new", data={
        "user_id": "jiro", "name": "佐藤次郎", "role": "user",
        "department_ids": [str(dept2_id)],
    }, follow_redirects=True)
    assert resp.status_code == 200
    assert "初期パスワード".encode() in resp.data
    with app.app_context():
        u = db.session.get(User, "jiro")
        assert u is not None
        assert u.must_change_password is True
        assert dept2_id in u.department_ids


def test_create_user_duplicate_id(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/users/new", data={
        "user_id": "taro", "name": "重複", "role": "user",
    })
    assert "既に使われています".encode() in resp.data


def test_edit_user_changes_role_and_departments(client, app):
    login(client, "admin", "adminpass1")
    with app.app_context():
        from app.models import Department
        dept1_id = Department.query.filter_by(name="第1営業部").first().id
    resp = client.post("/admin/users/hanako/edit", data={
        "name": "鈴木花子", "role": "admin", "department_ids": [str(dept1_id)],
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        u = db.session.get(User, "hanako")
        assert u.role == "admin"
        assert u.department_ids == {dept1_id}


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


def test_cannot_demote_last_sysadmin(client):
    login(client, "admin", "adminpass1")
    resp = client.post("/admin/users/admin/edit",
                       data={"name": "システム管理者", "role": "user"},
                       follow_redirects=True)
    assert "システム管理者が1人だけ".encode() in resp.data


def test_category_management(client, app):
    login(client, "admin", "adminpass1")
    with app.app_context():
        from app.models import Department
        dept2_id = Department.query.filter_by(name="第2営業部").first().id
    resp = client.post(f"/admin/categories?dept={dept2_id}", data={
        "code": "Xx", "name": "テストカテゴリー",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        from app.models import Category
        assert Category.query.filter_by(code="Xx").first() is not None
