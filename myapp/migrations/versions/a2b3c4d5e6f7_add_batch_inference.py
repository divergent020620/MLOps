"""add deploy_type and schedule to inferenceservice

Revision ID: a2b3c4d5e6f7
Revises: f1x2m3e4r5g6
Create Date: 2026-08-24 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a2b3c4d5e6f7'
down_revision = 'f1x2m3e4r5g6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('inferenceservice', schema=None) as batch_op:
        batch_op.add_column(sa.Column('deploy_type', sa.String(50), nullable=True, server_default='online', comment='部署方式：online在线服务/batch批处理'))
        batch_op.add_column(sa.Column('schedule', sa.String(200), nullable=True, server_default='', comment='批处理cron表达式，如 0 2 * * *'))


def downgrade():
    with op.batch_alter_table('inferenceservice', schema=None) as batch_op:
        batch_op.drop_column('schedule')
        batch_op.drop_column('deploy_type')