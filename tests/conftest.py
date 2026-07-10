"""pytest 共通フィクスチャ。インメモリDBで実データに影響を与えずにテストする。"""
import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import User, Status, Rank


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        # 最小限のマスタとユーザーを用意
        db.session.add_all([
            Status(name="進行中", sort_order=0),
            Status(name="受注", sort_order=1),
            Rank(name="A", sort_order=0),
            Rank(name="B", sort_order=1),
        ])
        admin = User(user_id="admin", name="管理者", role="admin",
                     is_active_flag=True, must_change_password=False)
        admin.set_password("adminpass1")
        member = User(user_id="taro", name="山田太郎", role="user",
                      is_active_flag=True, must_change_password=True)
        member.set_password("initpass12")
        db.session.add_all([admin, member])
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, user_id, password):
    return client.post("/login",
                       data={"user_id": user_id, "password": password},
                       follow_redirects=True)
