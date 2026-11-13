"""Additive schema; passwords and bearer tokens never enter operational JSON records."""
import sqlalchemy as sa

from ..db import JSONType, metadata

users = sa.Table(
    'pilot_users', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('username', sa.String(64), nullable=False, unique=True),
    sa.Column('name', sa.String(100), nullable=False),
    sa.Column('password_hash', sa.Text, nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
)
teams = sa.Table(
    'pilot_teams', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('name', sa.String(100), nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
)
memberships = sa.Table(
    'pilot_memberships', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('team_id', sa.String(64), sa.ForeignKey('pilot_teams.id'), nullable=False),
    sa.Column('user_id', sa.String(64), sa.ForeignKey('pilot_users.id'), nullable=False),
    sa.Column('role', sa.String(16), nullable=False),
    sa.Column('active', sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column('version', sa.Integer, nullable=False, server_default='1'),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.UniqueConstraint('team_id', 'user_id', name='pilot_membership_unique'),
    sa.CheckConstraint("role IN ('admin','engineer','operator','viewer')", name='pilot_membership_role'),
)
sessions = sa.Table(
    'pilot_sessions', metadata,
    sa.Column('token_hash', sa.String(64), primary_key=True),
    sa.Column('user_id', sa.String(64), sa.ForeignKey('pilot_users.id'), nullable=False),
    sa.Column('team_id', sa.String(64), sa.ForeignKey('pilot_teams.id'), nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('expires_at', sa.Float, nullable=False),
    sa.Column('revoked_at', sa.String(40)),
    sa.Index('pilot_sessions_user', 'user_id', 'team_id'),
)
invites = sa.Table(
    'pilot_invites', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('token_hash', sa.String(64), nullable=False, unique=True),
    sa.Column('team_id', sa.String(64), sa.ForeignKey('pilot_teams.id'), nullable=False),
    sa.Column('role', sa.String(16), nullable=False),
    sa.Column('created_by', sa.String(64), sa.ForeignKey('pilot_users.id'), nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('expires_at', sa.Float, nullable=False),
    sa.Column('used_at', sa.String(40)),
    sa.CheckConstraint("role IN ('admin','engineer','operator','viewer')", name='pilot_invite_role'),
)
auth_limits = sa.Table(
    'pilot_auth_limits', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('window', sa.BigInteger, nullable=False),
    sa.Column('attempts', sa.Integer, nullable=False),
)
records = sa.Table(
    'pilot_records', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('owner_id', sa.String(64), primary_key=True),
    sa.Column('kind', sa.String(24), nullable=False),
    sa.Column('version', sa.Integer, nullable=False, server_default='1'),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('updated_at', sa.String(40), nullable=False),
    sa.Column('payload', JSONType, nullable=False),
    sa.Index('pilot_records_owner_kind', 'owner_id', 'kind', 'created_at'),
)
