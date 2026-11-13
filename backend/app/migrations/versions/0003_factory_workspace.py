"""Team identity, revocable sessions and team-owned versioned factory records.

Revision ID: 0003
Revises: 0002
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None
JSONType = sa.JSON().with_variant(JSONB(), 'postgresql')


def upgrade():
    op.create_table('pilot_users',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('username', sa.String(64), nullable=False, unique=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('password_hash', sa.Text, nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))
    op.create_table('pilot_teams',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False))
    op.create_table('pilot_memberships',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('team_id', sa.String(64), sa.ForeignKey('pilot_teams.id'), nullable=False),
        sa.Column('user_id', sa.String(64), sa.ForeignKey('pilot_users.id'), nullable=False),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('active', sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.UniqueConstraint('team_id', 'user_id', name='pilot_membership_unique'),
        sa.CheckConstraint("role IN ('admin','engineer','operator','viewer')", name='pilot_membership_role'))
    op.create_table('pilot_sessions',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('user_id', sa.String(64), sa.ForeignKey('pilot_users.id'), nullable=False),
        sa.Column('team_id', sa.String(64), sa.ForeignKey('pilot_teams.id'), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('expires_at', sa.Float, nullable=False),
        sa.Column('revoked_at', sa.String(40)))
    op.create_index('pilot_sessions_user', 'pilot_sessions', ['user_id', 'team_id'])
    op.create_table('pilot_invites',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('team_id', sa.String(64), sa.ForeignKey('pilot_teams.id'), nullable=False),
        sa.Column('role', sa.String(16), nullable=False),
        sa.Column('created_by', sa.String(64), sa.ForeignKey('pilot_users.id'), nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('expires_at', sa.Float, nullable=False),
        sa.Column('used_at', sa.String(40)),
        sa.CheckConstraint("role IN ('admin','engineer','operator','viewer')", name='pilot_invite_role'))
    op.create_table('pilot_auth_limits',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('window', sa.BigInteger, nullable=False),
        sa.Column('attempts', sa.Integer, nullable=False))
    op.create_table('pilot_records',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('owner_id', sa.String(64), primary_key=True),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('version', sa.Integer, nullable=False, server_default='1'),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('updated_at', sa.String(40), nullable=False),
        sa.Column('payload', JSONType, nullable=False))
    op.create_index('pilot_records_owner_kind', 'pilot_records', ['owner_id', 'kind', 'created_at'])


def downgrade():
    for name in ('pilot_records', 'pilot_auth_limits', 'pilot_invites', 'pilot_sessions',
                 'pilot_memberships', 'pilot_teams', 'pilot_users'):
        op.drop_table(name)
