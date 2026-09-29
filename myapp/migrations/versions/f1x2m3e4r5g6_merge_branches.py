"""merge two heads: e3f4a5b6c7d8 + a1b2c3d4e5f6

Revision ID: f1x2m3e4r5g6
Revises: e3f4a5b6c7d8, a1b2c3d4e5f6
Create Date: 2026-08-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f1x2m3e4r5g6'
down_revision = ('e3f4a5b6c7d8', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
