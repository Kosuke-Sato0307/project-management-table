"""59期リニューアル: 案件をID主キー化、部門紐づけ・区分/カテゴリー/販管費を追加

抜本改修:
  - 旧 projects（案件番号主キー）を破棄し、整数ID主キーの新 projects を作成。
  - ユーザー↔部門の多対多(user_departments)、区分(kubun)、カテゴリー(categories)、
    販管費(sga) を追加。
  - 権限を3段階化。従来の全権 admin は sysadmin に更新する。
  - 未使用となる statuses マスタを削除。

Revision ID: a1b2c3d4e5f6
Revises: f3a7c9e21b04
Create Date: 2026-07-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = 'f3a7c9e21b04'
branch_labels = None
depends_on = None


def upgrade():
    # 1) 旧案件テーブルは新スキーマで作り直す（旧データは移行しない）
    op.drop_table('projects')
    # 案件ステータスは本要件では未使用
    op.drop_table('statuses')

    # 2) ユーザー↔部門 多対多
    op.create_table(
        'user_departments',
        sa.Column('user_id', sa.String(length=64), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
        sa.PrimaryKeyConstraint('user_id', 'department_id'),
    )

    # 3) 区分マスタ
    op.create_table(
        'kubun',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=32), nullable=False),
        sa.Column('is_plan', sa.Boolean(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    # 4) カテゴリーマスタ（部門別）
    op.create_table(
        'categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=True),
        sa.Column('code', sa.String(length=16), nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # 5) 販管費（月次・部門別）
    op.create_table(
        'sga',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('fiscal_period', sa.Integer(), nullable=False),
        sa.Column('month', sa.String(length=7), nullable=False),
        sa.Column('amount', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('department_id', 'fiscal_period', 'month',
                            name='uq_sga_dept_period_month'),
    )

    # 6) 新 案件テーブル（ID主キー）
    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('fiscal_period', sa.Integer(), nullable=False),
        sa.Column('accounting_month', sa.String(length=7), nullable=False),
        sa.Column('department_id', sa.Integer(), nullable=False),
        sa.Column('assignee_user_id', sa.String(length=64), nullable=True),
        sa.Column('kubun_id', sa.Integer(), nullable=True),
        sa.Column('category_id', sa.Integer(), nullable=True),
        sa.Column('project_name', sa.String(length=255), nullable=False),
        sa.Column('rank_id', sa.Integer(), nullable=True),
        sa.Column('sales', sa.Integer(), nullable=True),
        sa.Column('cost', sa.Integer(), nullable=True),
        sa.Column('estimated_hours', sa.Float(), nullable=True),
        sa.Column('actual_hours', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(length=128), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id'], ),
        sa.ForeignKeyConstraint(['assignee_user_id'], ['users.user_id'], ),
        sa.ForeignKeyConstraint(['kubun_id'], ['kubun.id'], ),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ),
        sa.ForeignKeyConstraint(['rank_id'], ['ranks.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )

    # 7) 従来の全権 admin をシステム管理者へ更新
    op.execute("UPDATE users SET role = 'sysadmin' WHERE role = 'admin'")


def downgrade():
    # 案件ステータスを戻す
    op.create_table(
        'statuses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.execute("UPDATE users SET role = 'admin' WHERE role = 'sysadmin'")

    op.drop_table('projects')
    op.drop_table('sga')
    op.drop_table('categories')
    op.drop_table('kubun')
    op.drop_table('user_departments')

    # 旧 案件テーブル（案件番号主キー）を復元
    op.create_table(
        'projects',
        sa.Column('project_no', sa.String(length=64), nullable=False),
        sa.Column('project_name', sa.String(length=255), nullable=False),
        sa.Column('customer_name', sa.String(length=255), nullable=True),
        sa.Column('status_id', sa.Integer(), nullable=True),
        sa.Column('rank_id', sa.Integer(), nullable=True),
        sa.Column('estimate_no', sa.String(length=64), nullable=True),
        sa.Column('amount_excl_tax', sa.Integer(), nullable=True),
        sa.Column('completion_month', sa.String(length=7), nullable=True),
        sa.Column('order_date', sa.Date(), nullable=True),
        sa.Column('sales_rep', sa.String(length=128), nullable=True),
        sa.Column('department', sa.String(length=128), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(length=128), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('updated_by', sa.String(length=128), nullable=True),
        sa.ForeignKeyConstraint(['rank_id'], ['ranks.id'], ),
        sa.ForeignKeyConstraint(['status_id'], ['statuses.id'], ),
        sa.PrimaryKeyConstraint('project_no'),
    )
