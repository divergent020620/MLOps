"""add announcement and platform_config tables

Revision ID: e3f4a5b6c7d8
Revises: 593366be4eff
Create Date: 2026-07-29 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e3f4a5b6c7d8'
down_revision = '593366be4eff'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'announcement',
        sa.Column('created_on', sa.DateTime(), nullable=True),
        sa.Column('changed_on', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='公告ID主键'),
        sa.Column('title', sa.String(length=200), nullable=False, comment='公告标题'),
        sa.Column('content', sa.Text(length=65536), nullable=True, comment='公告内容（Markdown格式）'),
        sa.Column('is_active', sa.Boolean(), nullable=True, comment='是否当前生效公告'),
        sa.Column('created_by_fk', sa.Integer(), nullable=True),
        sa.Column('changed_by_fk', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['changed_by_fk'], ['ab_user.id'], ),
        sa.ForeignKeyConstraint(['created_by_fk'], ['ab_user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table(
        'platform_config',
        sa.Column('created_on', sa.DateTime(), nullable=True),
        sa.Column('changed_on', sa.DateTime(), nullable=True),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False, comment='配置ID主键'),
        sa.Column('host_aliases', sa.Text(), nullable=True, comment='额外 hostAliases'),
        sa.Column('dns_nameservers', sa.Text(), nullable=True, comment='DNS nameservers'),
        sa.Column('dns_searches', sa.Text(), nullable=True, comment='DNS search domains'),
        sa.Column('dns_options', sa.Text(), nullable=True, comment='DNS options'),
        sa.Column('created_by_fk', sa.Integer(), nullable=True, comment='创建人ID'),
        sa.Column('changed_by_fk', sa.Integer(), nullable=True, comment='修改人ID'),
        sa.ForeignKeyConstraint(['changed_by_fk'], ['ab_user.id'], ),
        sa.ForeignKeyConstraint(['created_by_fk'], ['ab_user.id'], ),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('announcement')
    op.drop_table('platform_config')
