"""drop maintenance_start / maintenance_end columns from projects

保守開始日・保守終了日は本システムでは使用しないため、案件テーブルから削除する。

Revision ID: f3a7c9e21b04
Revises: d2d1104b59fe
Create Date: 2026-07-13 05:10:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f3a7c9e21b04'
down_revision = 'd2d1104b59fe'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite はカラム削除に ALTER が使えないため batch モードで行う。
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_column('maintenance_start')
        batch_op.drop_column('maintenance_end')


def downgrade():
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.add_column(sa.Column('maintenance_start', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('maintenance_end', sa.Date(), nullable=True))
