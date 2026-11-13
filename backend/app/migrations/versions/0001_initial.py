"""The three record tables the first SQLite release created.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(JSONB(), 'postgresql')


def upgrade():
    op.create_table(
        'inspections',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('scope_id', sa.String(32), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('payload', JSONType, nullable=False),
    )
    op.create_index('inspections_scope', 'inspections', ['scope_id', 'created_at'])
    op.create_table(
        'corrections',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('inspection_id', sa.String(64), sa.ForeignKey('inspections.id'), unique=True, nullable=False),
        sa.Column('scope_id', sa.String(32), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('payload', JSONType, nullable=False),
    )
    op.create_index('corrections_scope', 'corrections', ['scope_id', 'created_at'])
    op.create_table(
        'comparisons',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('scope_id', sa.String(32), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('payload', JSONType, nullable=False),
    )


def downgrade():
    op.drop_table('comparisons')
    op.drop_table('corrections')
    op.drop_table('inspections')
