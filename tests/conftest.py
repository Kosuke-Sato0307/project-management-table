"""pytest 共通フィクスチャ。インメモリDBで実データに影響を与えずにテストする。"""
import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import (User, Rank, Department, Kubun, Category, Project, Sga,
                        ROLE_SYSADMIN, ROLE_ADMIN, ROLE_USER)


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        _seed()
        yield app
        db.session.remove()
        db.drop_all()


def _seed():
    """3権限・2部門・マスタ・案件の最小データを用意する。"""
    # 部門
    dept2 = Department(name="第2営業部", sort_order=0)
    dept1 = Department(name="第1営業部", sort_order=1)
    db.session.add_all([dept2, dept1])
    db.session.flush()

    # 確度（○ が実績）
    ranks = {}
    for i, name in enumerate(["○", "A", "B", "C", "D", "E", "×"]):
        r = Rank(name=name, sort_order=i)
        db.session.add(r)
        ranks[name] = r

    # 区分
    kplan = Kubun(name="期初計画", is_plan=True, sort_order=0)
    knew = Kubun(name="新規", is_plan=False, sort_order=1)
    db.session.add_all([kplan, knew])

    # カテゴリー（第2営業部）
    cat_ri = Category(department=dept2, code="Ri", name="Ribbon Communications関連", sort_order=0)
    cat_or = Category(department=dept2, code="Or", name="Oracle関連", sort_order=1)
    db.session.add_all([cat_ri, cat_or])
    db.session.flush()

    # ユーザー
    sysadmin = User(user_id="admin", name="システム管理者", role=ROLE_SYSADMIN,
                    is_active_flag=True, must_change_password=False)
    sysadmin.set_password("adminpass1")
    manager = User(user_id="bucho", name="部門長", role=ROLE_ADMIN,
                   is_active_flag=True, must_change_password=False)
    manager.set_password("buchopass1")
    manager.departments = [dept2]
    taro = User(user_id="taro", name="山田太郎", role=ROLE_USER,
                is_active_flag=True, must_change_password=True)
    taro.set_password("initpass12")
    taro.departments = [dept2]
    hanako = User(user_id="hanako", name="鈴木花子", role=ROLE_USER,
                  is_active_flag=True, must_change_password=False)
    hanako.set_password("hanakopass1")
    hanako.departments = [dept2]
    db.session.add_all([sysadmin, manager, taro, hanako])
    db.session.flush()

    # 案件（第2営業部, 59期）
    # 期初計画（受注確定 ○）: 売上100万, 仕入60万 -> 粗利40万, 計上月 2026-09
    db.session.add(Project(
        department_id=dept2.id, fiscal_period=59, accounting_month="2026-09",
        assignee_user_id="hanako", kubun_id=kplan.id, category_id=cat_ri.id,
        rank_id=ranks["○"].id, project_name="計画案件A", sales=1000000, cost=600000,
        estimated_hours=10, actual_hours=8))
    # 新規（○）: 売上50万 仕入20万 -> 粗利30万, 2026-12(=2Q)
    db.session.add(Project(
        department_id=dept2.id, fiscal_period=59, accounting_month="2026-12",
        assignee_user_id="hanako", kubun_id=knew.id, category_id=cat_or.id,
        rank_id=ranks["○"].id, project_name="新規案件B", sales=500000, cost=200000))
    # 新規（確度B・実績外）: 売上80万 仕入50万, 2027-03(=3Q)
    db.session.add(Project(
        department_id=dept2.id, fiscal_period=59, accounting_month="2027-03",
        assignee_user_id="hanako", kubun_id=knew.id, category_id=cat_ri.id,
        rank_id=ranks["B"].id, project_name="見込案件C", sales=800000, cost=500000))

    # 販管費（2026-09 に10万）
    db.session.add(Sga(department_id=dept2.id, fiscal_period=59,
                       month="2026-09", amount=100000))

    db.session.commit()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, user_id, password):
    return client.post("/login",
                       data={"user_id": user_id, "password": password},
                       follow_redirects=True)
