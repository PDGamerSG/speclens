"""Real columns, shared spec text, jobs, spend ledger and budget.

Existing rows are backfilled from their JSON payload, and their specification text moves to spec_revisions.

Revision ID: 0002
Revises: 0001
"""
import hashlib
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

JSONType = sa.JSON().with_variant(JSONB(), 'postgresql')


def spec_id(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def upgrade():
    for name, columns in {
        'inspections': [
            sa.Column('owner_id', sa.String(64), nullable=False, server_default=''),
            sa.Column('verdict', sa.String(16)), sa.Column('defect_type', sa.String(32)),
            sa.Column('confidence', sa.Float), sa.Column('cost_usd', sa.Float), sa.Column('latency_ms', sa.Integer),
            sa.Column('memory_enabled', sa.Boolean), sa.Column('cited_memories', sa.Integer),
            sa.Column('spec_revision_id', sa.String(32))],
        'corrections': [
            sa.Column('owner_id', sa.String(64), nullable=False, server_default=''),
            sa.Column('verdict', sa.String(16)), sa.Column('defect_type', sa.String(32)),
            sa.Column('sync_status', sa.String(16), nullable=False, server_default='pending'),
            sa.Column('sync_attempts', sa.Integer, nullable=False, server_default='0'),
            sa.Column('next_sync_at', sa.Float)],
        'comparisons': [sa.Column('owner_id', sa.String(64), nullable=False, server_default='')],
    }.items():
        for column in columns:
            op.add_column(name, column)
    op.create_index('inspections_owner', 'inspections', ['owner_id', 'created_at'])
    op.create_index('corrections_outbox', 'corrections', ['sync_status', 'next_sync_at'])
    op.create_index('comparisons_scope', 'comparisons', ['scope_id', 'created_at'])

    op.create_table(
        'spec_revisions',
        sa.Column('id', sa.String(32), primary_key=True),
        sa.Column('spec_text', sa.Text, nullable=False),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('taxonomy', JSONType),
    )
    op.create_table(
        'jobs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('kind', sa.String(24), nullable=False),
        sa.Column('owner_id', sa.String(64), nullable=False, server_default=''),
        sa.Column('batch_id', sa.String(64)),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('payload', JSONType, nullable=False),
        sa.Column('result', JSONType), sa.Column('error', JSONType),
        sa.Column('attempts', sa.Integer, nullable=False, server_default='0'),
        sa.Column('run_after', sa.Float, nullable=False), sa.Column('locked_at', sa.Float),
        sa.Column('created_at', sa.String(40), nullable=False), sa.Column('updated_at', sa.Float, nullable=False),
    )
    op.create_index('jobs_queue', 'jobs', ['status', 'run_after'])
    op.create_index('jobs_batch', 'jobs', ['batch_id'])
    op.create_table(
        'model_calls',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('t', sa.Float, nullable=False), sa.Column('model', sa.String(48), nullable=False),
        sa.Column('op', sa.String(48), nullable=False), sa.Column('ms', sa.Integer, nullable=False),
        sa.Column('status', sa.String(24), nullable=False), sa.Column('cost_usd', sa.Float, nullable=False),
        sa.Column('run_id', sa.String(64)), sa.Column('prompt_tokens', sa.Integer),
        sa.Column('cached_tokens', sa.Integer), sa.Column('completion_tokens', sa.Integer),
        sa.Column('extra', JSONType),
    )
    op.create_index('model_calls_t', 'model_calls', ['t'])
    op.create_index('model_calls_run', 'model_calls', ['run_id'])
    budget = op.create_table(
        'budget',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('spent_usd', sa.Float, nullable=False, server_default='0'),
        sa.Column('reserved_usd', sa.Float, nullable=False, server_default='0'),
        sa.Column('prompt_tokens', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('cached_tokens', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('saved_usd', sa.Float, nullable=False, server_default='0'),
        sa.Column('imported_ledger', sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.bulk_insert(budget, [{'id': 1, 'spent_usd': 0, 'reserved_usd': 0, 'prompt_tokens': 0,
                             'cached_tokens': 0, 'saved_usd': 0, 'imported_ledger': False}])
    op.create_table(
        'benchmark_runs',
        sa.Column('id', sa.String(64), primary_key=True),
        sa.Column('created_at', sa.String(40), nullable=False),
        sa.Column('payload', JSONType, nullable=False),
    )
    backfill()


def backfill():
    connection = op.get_bind()
    now = datetime.now(timezone.utc).isoformat()
    specs = sa.table('spec_revisions', sa.column('id'), sa.column('spec_text'), sa.column('created_at'))
    known: set[str] = set()

    def strip(item: dict) -> dict:
        text = item.get('spec_text')
        if not isinstance(text, str):
            return item
        sid = spec_id(text)
        if sid not in known:
            connection.execute(specs.insert().values(id=sid, spec_text=text, created_at=now))
            known.add(sid)
        return {**{k: v for k, v in item.items() if k != 'spec_text'}, 'spec_revision_id': sid}

    def table(name, *extra):
        return sa.table(name, sa.column('id'), sa.column('payload', JSONType), *[sa.column(c) for c in extra])

    rows = table('inspections', 'owner_id', 'verdict', 'defect_type', 'confidence', 'cost_usd', 'latency_ms',
                 'memory_enabled', 'cited_memories', 'spec_revision_id')
    for id, payload in connection.execute(sa.select(rows.c.id, rows.c.payload)).all():
        item = strip(payload)
        connection.execute(rows.update().where(rows.c.id == id).values(
            payload=item, owner_id=item.get('owner_id', ''), verdict=item.get('verdict'),
            defect_type=item.get('type'), confidence=item.get('confidence'), cost_usd=item.get('cost_usd'),
            latency_ms=round(item['ms']) if isinstance(item.get('ms'), (int, float)) else None,
            memory_enabled=item.get('memory_enabled'), cited_memories=len(item.get('memories') or []),
            spec_revision_id=item.get('spec_revision_id')))

    rows = table('corrections', 'owner_id', 'verdict', 'defect_type', 'sync_status')
    for id, payload in connection.execute(sa.select(rows.c.id, rows.c.payload)).all():
        item = strip(payload)
        connection.execute(rows.update().where(rows.c.id == id).values(
            payload=item, owner_id=item.get('owner_id', ''), verdict=item.get('verdict'),
            defect_type=item.get('defect_type'), sync_status=item.get('sync_status', 'pending')))

    rows = table('comparisons', 'owner_id')
    for id, payload in connection.execute(sa.select(rows.c.id, rows.c.payload)).all():
        item = dict(payload)
        for arm in ('baseline', 'with_memory'):
            if isinstance(item.get(arm), dict):
                item[arm] = strip(item[arm])
        owner = (item.get('baseline') or {}).get('owner_id', '')
        connection.execute(rows.update().where(rows.c.id == id).values(payload=item, owner_id=owner))


def downgrade():
    for name in ('benchmark_runs', 'budget', 'model_calls', 'jobs', 'spec_revisions'):
        op.drop_table(name)
