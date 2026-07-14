"""権限モデル（User の閲覧/編集判定）と販管費入力のテスト。"""
from app.extensions import db
from app.models import User, Department, Project
from tests.conftest import login


def test_role_view_edit_matrix(app):
    with app.app_context():
        dept2 = Department.query.filter_by(name="第2営業部").first()
        dept1 = Department.query.filter_by(name="第1営業部").first()
        sysadmin = db.session.get(User, "admin")
        manager = db.session.get(User, "bucho")   # 第2営業部の管理者
        taro = db.session.get(User, "taro")        # 第2営業部の一般
        hanako = db.session.get(User, "hanako")    # 第2営業部の一般
        proj = Project.query.filter_by(project_name="計画案件A").first()  # hanako担当

        # 閲覧: sysadmin/manager は全部門、user は自部門のみ
        assert sysadmin.can_view_department(dept1.id) is True
        assert manager.can_view_department(dept1.id) is True
        assert taro.can_view_department(dept1.id) is False
        assert taro.can_view_department(dept2.id) is True

        # 部門編集: sysadmin=全、manager=自部門、user=不可
        assert sysadmin.can_edit_department(dept1.id) is True
        assert manager.can_edit_department(dept2.id) is True
        assert manager.can_edit_department(dept1.id) is False
        assert taro.can_edit_department(dept2.id) is False

        # 案件編集: sysadmin=全、manager=自部門、user=自担当のみ
        assert sysadmin.can_edit_project(proj) is True
        assert manager.can_edit_project(proj) is True
        assert hanako.can_edit_project(proj) is True     # 自分が担当
        assert taro.can_edit_project(proj) is False       # 他人担当


def test_multi_department_assignment(app):
    with app.app_context():
        dept2 = Department.query.filter_by(name="第2営業部").first()
        dept1 = Department.query.filter_by(name="第1営業部").first()
        hanako = db.session.get(User, "hanako")
        hanako.departments = [dept1, dept2]
        db.session.commit()
        assert hanako.department_ids == {dept1.id, dept2.id}
        assert hanako.can_view_department(dept1.id) is True


def test_sga_input_by_manager(client, app):
    with app.app_context():
        dept2_id = Department.query.filter_by(name="第2営業部").first().id
    login(client, "bucho", "buchopass1")
    resp = client.post(f"/analytics/sga?dept={dept2_id}", data={
        "m_2026-10": "50,000", "m_2026-11": "30000",
    }, follow_redirects=True)
    assert resp.status_code == 200
    with app.app_context():
        from app.models import Sga
        rows = {r.month: r.amount for r in Sga.query.filter_by(
            department_id=dept2_id, fiscal_period=59).all()}
        assert rows.get("2026-10") == 50000
        assert rows.get("2026-11") == 30000


def test_sga_input_forbidden_for_general_user(client, app):
    with app.app_context():
        dept2_id = Department.query.filter_by(name="第2営業部").first().id
    login(client, "hanako", "hanakopass1")
    resp = client.post(f"/analytics/sga?dept={dept2_id}",
                       data={"m_2026-10": "1000"})
    assert resp.status_code == 403
