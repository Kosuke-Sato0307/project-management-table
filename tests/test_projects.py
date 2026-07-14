"""案件（案件管理表）のCRUD・権限・月グルーピングのテスト。"""
from app.extensions import db
from app.models import Project, Department, Kubun, Rank, Category
from tests.conftest import login


def _dept2_id(app):
    with app.app_context():
        return Department.query.filter_by(name="第2営業部").first().id


def _create(client, dept_id, name="テスト案件", month="2026-09", **extra):
    data = {"accounting_month": month, "project_name": name}
    data.update(extra)
    return client.post(f"/projects/new?dept={dept_id}", data=data,
                       follow_redirects=True)


def test_projects_requires_login(client):
    resp = client.get("/projects", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_sysadmin_can_create_project(client, app):
    login(client, "admin", "adminpass1")
    dept_id = _dept2_id(app)
    resp = _create(client, dept_id, "新規案件A", sales="1,000,000", cost="400,000")
    assert resp.status_code == 200
    with app.app_context():
        p = Project.query.filter_by(project_name="新規案件A").first()
        assert p is not None
        assert p.sales == 1000000 and p.cost == 400000
        assert p.gross_profit == 600000
        assert p.created_by == "admin"
        assert p.fiscal_period == 59


def test_project_name_required(client, app):
    login(client, "admin", "adminpass1")
    dept_id = _dept2_id(app)
    resp = _create(client, dept_id, name="")
    assert "案件名は必須".encode() in resp.data


def test_accounting_month_required(client, app):
    login(client, "admin", "adminpass1")
    dept_id = _dept2_id(app)
    resp = client.post(f"/projects/new?dept={dept_id}",
                       data={"project_name": "月なし", "accounting_month": ""},
                       follow_redirects=True)
    assert "計上月は必須".encode() in resp.data


def test_sales_accepts_comma_and_fullwidth(client, app):
    login(client, "admin", "adminpass1")
    dept_id = _dept2_id(app)
    _create(client, dept_id, "金額カンマ", sales="１，２３４，５６７")
    with app.app_context():
        assert Project.query.filter_by(project_name="金額カンマ").first().sales == 1234567


def test_general_user_create_forces_self_as_assignee(client, app):
    login(client, "hanako", "hanakopass1")
    dept_id = _dept2_id(app)
    # 他人(taro)を担当に指定しても自分(hanako)に固定される
    _create(client, dept_id, "自分の案件", assignee_user_id="taro")
    with app.app_context():
        p = Project.query.filter_by(project_name="自分の案件").first()
        assert p.assignee_user_id == "hanako"


def test_general_user_cannot_edit_others_project(client, app):
    # taro が hanako 担当の案件を編集しようとすると 403
    with app.app_context():
        p = Project.query.filter_by(project_name="計画案件A").first()
        pid = p.id
        assert p.assignee_user_id == "hanako"
    login(client, "taro", "initpass12")
    # 初回PW変更ガードを外す
    _skip_pw(client)
    resp = client.get(f"/projects/{pid}/edit")
    assert resp.status_code == 403


def test_general_user_can_view_department_list(client, app):
    login(client, "hanako", "hanakopass1")
    dept_id = _dept2_id(app)
    resp = client.get(f"/projects?dept={dept_id}")
    assert resp.status_code == 200
    assert "計画案件A".encode() in resp.data


def test_general_user_cannot_view_other_department(client, app):
    with app.app_context():
        dept1_id = Department.query.filter_by(name="第1営業部").first().id
    login(client, "hanako", "hanakopass1")
    resp = client.get(f"/projects?dept={dept1_id}")
    assert resp.status_code == 403


def test_manager_can_view_all_but_edit_only_own_dept(client, app):
    with app.app_context():
        dept1_id = Department.query.filter_by(name="第1営業部").first().id
        p = Project.query.filter_by(project_name="計画案件A").first()
        pid = p.id
    login(client, "bucho", "buchopass1")
    # 他部門(第1営業部)も閲覧可
    assert client.get(f"/projects?dept={dept1_id}").status_code == 200
    # 自部門(第2営業部)の案件は編集可
    assert client.get(f"/projects/{pid}/edit").status_code == 200


def test_manager_cannot_edit_other_department_project(client, app):
    # 第1営業部の案件を作って、第2営業部長(bucho)が編集不可を確認
    with app.app_context():
        dept1 = Department.query.filter_by(name="第1営業部").first()
        p = Project(department_id=dept1.id, fiscal_period=59,
                    accounting_month="2026-09", project_name="他部門案件")
        db.session.add(p)
        db.session.commit()
        pid = p.id
    login(client, "bucho", "buchopass1")
    resp = client.get(f"/projects/{pid}/edit")
    assert resp.status_code == 403


def test_edit_and_delete_project(client, app):
    login(client, "admin", "adminpass1")
    dept_id = _dept2_id(app)
    _create(client, dept_id, "編集対象")
    with app.app_context():
        pid = Project.query.filter_by(project_name="編集対象").first().id
    resp = client.post(f"/projects/{pid}/edit", data={
        "accounting_month": "2026-10", "project_name": "編集後",
    }, follow_redirects=True)
    assert "編集後".encode() in resp.data
    with app.app_context():
        p = db.session.get(Project, pid)
        assert p.project_name == "編集後"
        assert p.accounting_month == "2026-10"
    resp = client.post(f"/projects/{pid}/delete", follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(Project, pid) is None


def test_month_grouping_shows_subtotal(client, app):
    login(client, "admin", "adminpass1")
    dept_id = _dept2_id(app)
    resp = client.get(f"/projects?dept={dept_id}")
    html = resp.data.decode()
    # 2026/9 の見出しと売上小計（計画案件A: 100万）が出る
    assert "2026/9" in html
    assert "1,000,000" in html


def _skip_pw(client):
    """初回PW変更を済ませてガードを外す。"""
    client.post("/change-password", data={
        "current_password": "initpass12",
        "new_password": "brandnew99",
        "new_password_confirm": "brandnew99",
    }, follow_redirects=True)
