"""add hdfs_path column to dataset

Revision ID: a1b2c3d4e5f6
Revises: 354ff240b2e7
Create Date: 2026-07-29 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '354ff240b2e7'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('dataset', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hdfs_path', sa.String(1000), nullable=True, comment='HDFS源路径(相对base_path)'))


def downgrade():
    with op.batch_alter_table('dataset', schema=None) as batch_op:
        batch_op.drop_column('hdfs_path')
