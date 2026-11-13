"""One database for records, jobs and spend: Postgres in production (DATABASE_URL), a SQLite file locally.

Run `python -m app.db upgrade` to apply migrations. Opening an engine also applies them, so local runs and
tests need no extra step; on Postgres an advisory lock keeps the API and worker from migrating at once.
"""
from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

JSONType = sa.JSON().with_variant(JSONB(), 'postgresql')
MIGRATIONS = Path(__file__).with_name('migrations')
MIGRATION_LOCK = 7262021
metadata = sa.MetaData()

spec_revisions = sa.Table(
    'spec_revisions', metadata,
    sa.Column('id', sa.String(32), primary_key=True),
    sa.Column('spec_text', sa.Text, nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('taxonomy', JSONType),
)

inspections = sa.Table(
    'inspections', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('scope_id', sa.String(32), nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('payload', JSONType, nullable=False),
    sa.Column('owner_id', sa.String(64), nullable=False, server_default=''),
    sa.Column('verdict', sa.String(16)),
    sa.Column('defect_type', sa.String(32)),
    sa.Column('confidence', sa.Float),
    sa.Column('cost_usd', sa.Float),
    sa.Column('latency_ms', sa.Integer),
    sa.Column('memory_enabled', sa.Boolean),
    sa.Column('cited_memories', sa.Integer),
    sa.Column('spec_revision_id', sa.String(32)),
    sa.Index('inspections_scope', 'scope_id', 'created_at'),
    sa.Index('inspections_owner', 'owner_id', 'created_at'),
)

corrections = sa.Table(
    'corrections', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('inspection_id', sa.String(64), sa.ForeignKey('inspections.id'), unique=True, nullable=False),
    sa.Column('scope_id', sa.String(32), nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('payload', JSONType, nullable=False),
    sa.Column('owner_id', sa.String(64), nullable=False, server_default=''),
    sa.Column('verdict', sa.String(16)),
    sa.Column('defect_type', sa.String(32)),
    sa.Column('sync_status', sa.String(16), nullable=False, server_default='pending'),
    sa.Column('sync_attempts', sa.Integer, nullable=False, server_default='0'),
    sa.Column('next_sync_at', sa.Float),
    sa.Index('corrections_scope', 'scope_id', 'created_at'),
    sa.Index('corrections_outbox', 'sync_status', 'next_sync_at'),
)

comparisons = sa.Table(
    'comparisons', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('scope_id', sa.String(32), nullable=False),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('payload', JSONType, nullable=False),
    sa.Column('owner_id', sa.String(64), nullable=False, server_default=''),
    sa.Index('comparisons_scope', 'scope_id', 'created_at'),
)

jobs = sa.Table(
    'jobs', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('kind', sa.String(24), nullable=False),
    sa.Column('owner_id', sa.String(64), nullable=False, server_default=''),
    sa.Column('batch_id', sa.String(64)),
    sa.Column('status', sa.String(16), nullable=False),
    sa.Column('payload', JSONType, nullable=False),
    sa.Column('result', JSONType),
    sa.Column('error', JSONType),
    sa.Column('attempts', sa.Integer, nullable=False, server_default='0'),
    sa.Column('run_after', sa.Float, nullable=False),
    sa.Column('locked_at', sa.Float),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('updated_at', sa.Float, nullable=False),
    sa.Index('jobs_queue', 'status', 'run_after'),
    sa.Index('jobs_batch', 'batch_id'),
)

model_calls = sa.Table(
    'model_calls', metadata,
    sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
    sa.Column('t', sa.Float, nullable=False),
    sa.Column('model', sa.String(48), nullable=False),
    sa.Column('op', sa.String(48), nullable=False),
    sa.Column('ms', sa.Integer, nullable=False),
    sa.Column('status', sa.String(24), nullable=False),
    sa.Column('cost_usd', sa.Float, nullable=False),
    sa.Column('run_id', sa.String(64)),
    sa.Column('prompt_tokens', sa.Integer),
    sa.Column('cached_tokens', sa.Integer),
    sa.Column('completion_tokens', sa.Integer),
    sa.Column('extra', JSONType),
    sa.Index('model_calls_t', 't'),
    sa.Index('model_calls_run', 'run_id'),
)

# One row. Counters move with every call so status reads stay O(1) however long the history grows.
budget = sa.Table(
    'budget', metadata,
    sa.Column('id', sa.Integer, primary_key=True),
    sa.Column('spent_usd', sa.Float, nullable=False, server_default='0'),
    sa.Column('reserved_usd', sa.Float, nullable=False, server_default='0'),
    sa.Column('prompt_tokens', sa.BigInteger, nullable=False, server_default='0'),
    sa.Column('cached_tokens', sa.BigInteger, nullable=False, server_default='0'),
    sa.Column('saved_usd', sa.Float, nullable=False, server_default='0'),
    sa.Column('imported_ledger', sa.Boolean, nullable=False, server_default=sa.false()),
)

benchmark_runs = sa.Table(
    'benchmark_runs', metadata,
    sa.Column('id', sa.String(64), primary_key=True),
    sa.Column('created_at', sa.String(40), nullable=False),
    sa.Column('payload', JSONType, nullable=False),
)

# Register the additive factory schema with the same metadata and engine.
from .pilot import tables as pilot_tables  # noqa: E402,F401


_engines: dict[str, sa.Engine] = {}
_lock = threading.Lock()


def normalize_url(url: str) -> str:
    """Render hands out postgres:// URLs. SQLAlchemy needs the psycopg 3 driver named."""
    url = url.strip()
    for prefix in ('postgres://', 'postgresql://'):
        if url.startswith(prefix):
            return 'postgresql+psycopg://' + url[len(prefix):]
    return url


def default_url() -> str:
    from .config import VAR
    return normalize_url(os.environ.get('DATABASE_URL', '')) or f'sqlite:///{VAR / "speclens.sqlite3"}'


def as_url(target: str | Path | None) -> str:
    if target is None:
        return default_url()
    text = str(target)
    return normalize_url(text) if '://' in text else f'sqlite:///{Path(text)}'


def engine(target: str | Path | None = None) -> sa.Engine:
    url = as_url(target)
    with _lock:
        if url not in _engines:
            if url.startswith('sqlite'):
                if url.startswith('sqlite:///'):
                    Path(url[len('sqlite:///'):]).parent.mkdir(parents=True, exist_ok=True)
                created = sa.create_engine(url, connect_args={'timeout': 15, 'check_same_thread': False})

                @sa.event.listens_for(created, 'connect')
                def _sqlite_settings(connection, _record):
                    cursor = connection.cursor()
                    cursor.execute('PRAGMA journal_mode=WAL')
                    cursor.execute('PRAGMA foreign_keys=ON')
                    cursor.execute('PRAGMA busy_timeout=15000')
                    cursor.close()
            else:
                created = sa.create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
            upgrade(created)
            _engines[url] = created
        return _engines[url]


def upgrade(target: sa.Engine) -> None:
    from alembic import command
    from alembic.config import Config

    config = Config()
    config.set_main_option('script_location', str(MIGRATIONS))
    with target.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(sa.text('SELECT pg_advisory_xact_lock(:key)'), {'key': MIGRATION_LOCK})
        tables = set(sa.inspect(connection).get_table_names())
        config.attributes['connection'] = connection
        # Databases created before migrations existed already hold the first revision's tables.
        if 'inspections' in tables and 'alembic_version' not in tables:
            command.stamp(config, '0001')
        command.upgrade(config, 'head')


def upsert_ignore(connection: sa.Connection, table: sa.Table, values: dict) -> None:
    """Insert unless the primary key exists. Both dialects support ON CONFLICT DO NOTHING."""
    if connection.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    connection.execute(insert(table).values(**values).on_conflict_do_nothing())


if __name__ == '__main__':
    if sys.argv[1:] != ['upgrade']:
        sys.exit('Usage: python -m app.db upgrade')
    engine()
    print('Database is at the latest migration.')
