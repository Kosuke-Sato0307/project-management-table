"""案件に取引先/エンドユーザ/商品カテゴリ/担当者名スナップショットを追加し、
商品カテゴリマスタと部門長の閲覧・編集可能部門(多対多)を新設する。

改修点:
  - projects に client_name / end_user_name / product_category_id / assignee_name を追加。
    既存行の assignee_name は users.name からバックフィルする（担当ユーザー削除後の氏名保持）。
  - product_categories（部門別の商品カテゴリマスタ）を新設し、第2営業部の初期値を投入。
  - user_manageable_departments（部門長の閲覧・編集可能部門・所属とは別枠）を新設。

Revision ID: c4d5e6f7a8b9
Revises: b2c3d4e5f6a7
Create Date: 2026-07-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c4d5e6f7a8b9'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    # 1) 商品カテゴリマスタ（部門別）
    op.create_table(
        'product_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # 2) 部門長の閲覧・編集可能部門（所属とは別枠の多対多）
    op.create_table(
        'user_manageable_departments',
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'department_id'),
    )

    # 3) 案件に新列を追加
    with op.batch_alter_table('projects') as batch:
        batch.add_column(sa.Column('assignee_name', sa.String(length=128), nullable=True))
        batch.add_column(sa.Column('client_name', sa.String(length=255), nullable=True))
        batch.add_column(sa.Column('end_user_name', sa.String(length=255), nullable=True))
        batch.add_column(sa.Column('product_category_id', sa.Integer(), nullable=True))
        batch.create_foreign_key('fk_projects_product_category', 'product_categories',
                                 ['product_category_id'], ['id'])

    # 4) 既存案件の担当者名をバックフィル（削除後も氏名を残せるように）
    op.execute(
        "UPDATE projects SET assignee_name = "
        "(SELECT name FROM users WHERE users.user_id = projects.assignee_user_id) "
        "WHERE assignee_user_id IS NOT NULL"
    )

    # 5) 第2営業部の商品カテゴリ初期値を投入
    conn = op.get_bind()
    dept2 = conn.execute(
        sa.text("SELECT id FROM departments WHERE name = :n"),
        {"n": "第2営業部"}
    ).fetchone()
    if dept2:
        dept2_id = dept2[0]
        defaults = ["GW-保守", "GW-運用", "GW-構築", "GW-販売", "音声-保守",
                    "マンション", "その他"]
        for i, name in enumerate(defaults):
            exists = conn.execute(
                sa.text("SELECT 1 FROM product_categories "
                        "WHERE department_id = :d AND name = :n"),
                {"d": dept2_id, "n": name}
            ).fetchone()
            if not exists:
                conn.execute(
                    sa.text("INSERT INTO product_categories "
                            "(department_id, name, sort_order, is_active) "
                            "VALUES (:d, :n, :s, 1)"),
                    {"d": dept2_id, "n": name, "s": i}
                )


def downgrade():
    with op.batch_alter_table('projects') as batch:
        batch.drop_constraint('fk_projects_product_category', type_='foreignkey')
        batch.drop_column('product_category_id')
        batch.drop_column('end_user_name')
        batch.drop_column('client_name')
        batch.drop_column('assignee_name')
    op.drop_table('user_manageable_departments')
    op.drop_table('product_categories')
