"""案件に plan_type 列を追加（期初計画/中期計画/案件管理の3データセット化）

計画/実績の判定を Kubun.is_plan から Project.plan_type へ移行する。
  - initial   … 期初計画（計画値）
  - midterm   … 中期計画
  - management … 案件管理（実績見込み。確度○を実績値として算出）

既存データは、区分が「期初計画」(kubun.is_plan=1) の案件を initial に、
それ以外を management にバックフィルし、従来の予実集計の数字を維持する。

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    # 1) 列を追加（既存行は server_default で management になる）
    op.add_column(
        'projects',
        sa.Column('plan_type', sa.String(length=16), nullable=False,
                  server_default='management'),
    )
    # 2) 既存の期初計画（区分 is_plan=1）を initial に移行
    #    ※ 代替方針: 既存を全て management に寄せ、期初計画を改めてインポート
    #      させたい場合は、以下の UPDATE を削除する。
    op.execute(
        "UPDATE projects SET plan_type='initial' "
        "WHERE kubun_id IN (SELECT id FROM kubun WHERE is_plan=1)"
    )
    # 3) 絞り込み用インデックス
    op.create_index('ix_projects_plan_type', 'projects', ['plan_type'])


def downgrade():
    op.drop_index('ix_projects_plan_type', table_name='projects')
    op.drop_column('projects', 'plan_type')
