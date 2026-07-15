"""数字まとめ（集計ロジック calc.py）のテスト。

conftest の第2営業部・59期データ（計画/実績は plan_type で区別）:
  - 計画案件A: 期初計画(initial)/2026-09(1Q,上期)/売上100万 仕入60万 粗利40万 (hanako)
  - 中期案件M: 中期計画(midterm)/2026-09(1Q,上期)/売上120万 仕入70万 (hanako)
  - 実績A':   案件管理(management)/確度○/2026-09(1Q,上期)/売上100万 仕入60万 粗利40万 (hanako)
  - 新規案件B: 案件管理(management)/確度○/2026-12(2Q,上期)/売上50万 仕入20万 粗利30万 (hanako)
  - 見込案件C: 案件管理(management)/確度B(実績外)/2027-03(3Q,下期)/売上80万 仕入50万 粗利30万 (hanako)
  - 販管費 2026-09: 10万
実績 = 案件管理 かつ 確度○ ／ 期初計画 = initial ／ 中期計画 = midterm。
"""
from app.analytics import calc
from app.models import Department, Project, Category, Rank


def _dept_and_projects(app):
    dept = Department.query.filter_by(name="第2営業部").first()
    projects = Project.query.filter_by(department_id=dept.id, fiscal_period=59).all()
    return dept, projects


def test_yojitsu_full_sales(app):
    with app.app_context():
        dept, projects = _dept_and_projects(app)
        tables = calc.yojitsu(dept, projects, 59, "full")
        sales_table = next(t for t in tables if t["metric"] == "売上")
        total = sales_table["total"]["cells"][0]
        assert total["plan"] == 1000000        # 期初計画のみ（A）
        assert total["midterm"] == 1200000     # 中期計画のみ（M）
        assert total["actual"] == 1500000      # 案件管理×確度○（A'+B）
        assert total["var"] == 500000
        assert round(total["rate"], 1) == 150.0


def test_yojitsu_full_gross(app):
    with app.app_context():
        dept, projects = _dept_and_projects(app)
        tables = calc.yojitsu(dept, projects, 59, "full")
        gross_table = next(t for t in tables if t["metric"] == "売上総利益")
        total = gross_table["total"]["cells"][0]
        assert total["plan"] == 400000
        assert total["actual"] == 700000       # 40万 + 30万


def test_yojitsu_quarter_buckets(app):
    with app.app_context():
        dept, projects = _dept_and_projects(app)
        tables = calc.yojitsu(dept, projects, 59, "quarter")
        sales_table = next(t for t in tables if t["metric"] == "売上")
        assert sales_table["headers"] == ["1Q", "2Q", "3Q", "4Q"]
        cells = sales_table["total"]["cells"]
        # 1Q: 計画案件A（実績100万・計画100万）
        assert cells[0]["actual"] == 1000000 and cells[0]["plan"] == 1000000
        # 2Q: 新規案件B（実績50万・計画0）
        assert cells[1]["actual"] == 500000 and cells[1]["plan"] == 0
        # 3Q: 見込案件C は確度Bなので実績0
        assert cells[2]["actual"] == 0


def test_soneki_full(app):
    with app.app_context():
        dept, projects = _dept_and_projects(app)
        sga = {"2026-09": 100000}
        data = calc.soneki(dept, projects, 59, "full", sga)
        total = data["total"][0]
        assert total["sales"] == 1500000       # 確度○のみ
        assert total["cost"] == 800000
        assert total["gross"] == 700000
        assert round(total["margin"], 1) == 46.7
        assert data["sga"][0] == 100000
        assert data["balance"][0] == 600000    # 粗利70万 − 販管費10万


def test_by_category(app):
    with app.app_context():
        dept, projects = _dept_and_projects(app)
        categories = Category.query.filter_by(department_id=dept.id).order_by(
            Category.sort_order).all()
        data = calc.by_category(categories, projects)
        rows = {r["name"]: r for r in data["rows"]}
        ri = rows["Ri（Ribbon Communications関連）"]
        assert ri["sales_plan"] == 1000000     # 計画案件A
        assert ri["sales_actual"] == 1000000   # A(○) のみ、C(B)は実績外
        assert ri["gross_plan"] == 400000
        assert ri["gross_actual"] == 400000
        orc = rows["Or（Oracle関連）"]
        assert orc["sales_actual"] == 500000
        assert orc["gross_actual"] == 300000
        assert data["total"]["sales_actual"] == 1500000


def test_by_rank_all_projects(app):
    with app.app_context():
        dept, projects = _dept_and_projects(app)
        ranks = Rank.query.filter_by(is_active=True).order_by(Rank.sort_order).all()
        data = calc.by_rank(ranks, projects)
        rows = {r["name"]: r for r in data["rows"]}
        assert rows["○"]["sales"] == 1500000   # A + B
        assert rows["○"]["gross"] == 700000
        assert rows["B"]["sales"] == 800000     # C（実績外だが確度別には含む）
        assert data["total"]["sales"] == 2300000


def test_analytics_pages_load(client, app):
    from tests.conftest import login
    login(client, "admin", "adminpass1")
    with app.app_context():
        did = Department.query.filter_by(name="第2営業部").first().id
    for path in [f"/analytics/yojitsu?dept={did}",
                 f"/analytics/soneki?dept={did}&gran=quarter",
                 f"/analytics/category?dept={did}",
                 f"/analytics/product-category?dept={did}",
                 f"/analytics/rank?dept={did}", f"/analytics/sga?dept={did}"]:
        resp = client.get(path)
        assert resp.status_code == 200, path


def test_by_product_category(app):
    with app.app_context():
        from app.models import ProductCategory
        dept, projects = _dept_and_projects(app)
        pcs = ProductCategory.query.filter_by(department_id=dept.id).order_by(
            ProductCategory.sort_order).all()
        data = calc.by_product_category(pcs, projects)
        rows = {r["name"]: r for r in data["rows"]}
        # GW-保守: 計画案件A(initial) 100万 / 実績A'(○) 100万
        assert rows["GW-保守"]["sales_plan"] == 1000000
        assert rows["GW-保守"]["sales_actual"] == 1000000
        # 音声-保守: 新規案件B(○) 50万（計画なし）
        assert rows["音声-保守"]["sales_actual"] == 500000
        assert rows["音声-保守"]["sales_plan"] == 0
        assert data["total"]["sales_actual"] == 1500000
