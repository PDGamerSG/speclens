"""The store runs unchanged on SQLite and Postgres, migrates old SQLite files, and keeps one copy of each spec.

Set SPECLENS_TEST_DATABASE_URL to also run these tests against a Postgres server.
"""
import json
import os
import sqlite3
import uuid

import pytest
import sqlalchemy as sa

from app import db
from app.workspace.store import Scope, Store

TARGETS = ['sqlite'] + (['postgres'] if os.environ.get('SPECLENS_TEST_DATABASE_URL') else [])


@pytest.fixture(params=TARGETS)
def store(request, tmp_path):
    if request.param == 'sqlite':
        return Store(tmp_path / 'records.sqlite3')
    return Store(os.environ['SPECLENS_TEST_DATABASE_URL'])


def scope(spec='Reject every ink marking.'):
    # A unique factory keeps Postgres runs independent, because they share one database.
    return Scope(factory=f'Factory {uuid.uuid4().hex[:8]}', part_family='Whole hazelnut', spec_text=spec)


def inspection(s, id=None, created_at='2026-11-07T12:00:00+00:00', verdict='good'):
    return {'id': id or f'insp-{uuid.uuid4().hex[:16]}', 'scope_id': s.id, 'owner_id': 'owner-a', 'factory': s.factory,
            'part_family': s.part_family, 'spec_text': s.spec_text, 'image_sha256': 'abc', 'filename': 'part.png',
            'verdict': verdict, 'type': 'good' if verdict == 'good' else 'print', 'rationale': 'A smooth highlight.',
            'image_url': '/files/workspace/x.jpg', 'memory_enabled': True,
            'memories': [{'source_id': 'c1', 'text': 'Reject ink.'}], 'cited_ids': ['c1'], 'confidence': 0.8, 'ms': 1234.4,
            'cost_usd': 0.0035, 'created_at': created_at}


def test_records_round_trip_with_their_specification(store):
    s = scope()
    saved = store.add_inspection(inspection(s))
    got = store.inspection(saved['id'])
    assert got['spec_text'] == s.spec_text
    assert got['memories'] == [{'source_id': 'c1', 'text': 'Reject ink.'}]
    assert 'spec_text' not in store.inspections(s.id, with_spec=False)[0]


def test_the_specification_is_stored_once_and_columns_are_queryable(store):
    s = scope(spec=f'Reject cracks. {uuid.uuid4().hex}')
    for verdict in ('good', 'defect'):
        store.add_inspection(inspection(s, verdict=verdict))
    with store.engine.connect() as c:
        specs = c.execute(sa.select(sa.func.count()).select_from(db.spec_revisions)
                          .where(db.spec_revisions.c.id == s.spec_revision_id)).scalar_one()
        payloads = c.execute(sa.select(db.inspections.c.payload).where(db.inspections.c.scope_id == s.id)).scalars().all()
        rejects = c.execute(sa.select(sa.func.count()).select_from(db.inspections).where(
            db.inspections.c.scope_id == s.id, db.inspections.c.verdict == 'defect',
            db.inspections.c.latency_ms == 1234, db.inspections.c.cited_memories == 1)).scalar_one()
    assert specs == 1
    assert all('spec_text' not in p for p in payloads)
    assert rejects == 1


def test_history_pages_by_creation_time(store):
    s = scope()
    for minute in range(5):
        store.add_inspection(inspection(s, id=f'insp-{s.id}-{minute}', created_at=f'2026-11-07T12:0{minute}:00+00:00'))
    first = store.inspections(s.id, limit=2)
    second = store.inspections(s.id, limit=2, before=first[-1]['created_at'])
    assert [i['created_at'][14:16] for i in first + second] == ['04', '03', '02', '01']
    assert store.count_inspections(s.id) == 5


def test_history_cursor_preserves_records_with_the_same_timestamp(store):
    s = scope()
    for n in range(5):
        store.add_inspection(inspection(s, id=f'insp-{s.id}-{n}', created_at='2026-11-07T12:00:00+00:00'))
    first = store.inspections(s.id, limit=2)
    cursor = f'{first[-1]["created_at"]}|{first[-1]["id"]}'
    second = store.inspections(s.id, limit=3, before=cursor)
    assert len(first + second) == 5
    assert len({i['id'] for i in first + second}) == 5


def test_a_second_correction_is_refused_and_sync_never_reverts(store):
    s = scope()
    item = store.add_inspection(inspection(s))
    c = store.add_correction(item['id'], verdict='defect', defect_type='print', rule_text='Reject ink.', reviewer='QA')
    with pytest.raises(ValueError):
        store.add_correction(item['id'], verdict='good', defect_type='good', rule_text='Accept ink.', reviewer='QA')
    assert c['id'] in store.due_corrections(limit=1000)
    assert store.mark_sync(c['id'], 'synced')['sync_status'] == 'synced'
    assert store.mark_sync(c['id'], 'pending', 'late failure')['sync_status'] == 'synced'
    assert c['id'] not in store.due_corrections(limit=1000)
    assert store.correction(c['id'])['spec_text'] == s.spec_text


def test_comparisons_keep_both_arms_and_their_specification(store):
    s = scope()
    arm = inspection(s)
    store.add_comparison({'id': f'compare-{uuid.uuid4().hex[:16]}', 'scope_id': s.id, 'created_at': '2026-11-07T12:00:00Z',
                          'baseline': arm, 'with_memory': {**arm, 'id': 'other'}})
    pair = store.comparisons(s.id)[0]
    assert pair['baseline']['spec_text'] == pair['with_memory']['spec_text'] == s.spec_text
    assert 'spec_text' not in store.comparisons(s.id, with_spec=False)[0]['baseline']


@pytest.mark.parametrize('sync_status', ['synced', 'pending'])
def test_a_database_from_the_first_release_is_migrated_in_place(tmp_path, sync_status):
    path = tmp_path / 'legacy.sqlite3'
    s = scope()
    old = inspection(s, id='insp-legacy')
    legacy = sqlite3.connect(path)
    legacy.executescript('''
        CREATE TABLE inspections (id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE INDEX inspections_scope ON inspections(scope_id, created_at);
        CREATE TABLE corrections (id TEXT PRIMARY KEY, inspection_id TEXT UNIQUE NOT NULL, scope_id TEXT NOT NULL,
            created_at TEXT NOT NULL, payload TEXT NOT NULL, FOREIGN KEY(inspection_id) REFERENCES inspections(id));
        CREATE INDEX corrections_scope ON corrections(scope_id, created_at);
        CREATE TABLE comparisons (id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
    ''')
    legacy.execute('INSERT INTO inspections VALUES (?, ?, ?, ?)', (old['id'], s.id, old['created_at'], json.dumps(old)))
    correction = {'id': 'correction-legacy', 'inspection_id': old['id'], 'scope_id': s.id, 'owner_id': 'owner-a',
                  'spec_text': s.spec_text, 'factory': s.factory, 'part_family': s.part_family, 'verdict': 'defect',
                  'defect_type': 'print', 'sync_status': sync_status, 'created_at': old['created_at']}
    legacy.execute('INSERT INTO corrections VALUES (?, ?, ?, ?, ?)',
                   (correction['id'], old['id'], s.id, old['created_at'], json.dumps(correction)))
    legacy.commit()
    legacy.close()

    store = Store(path)
    assert store.inspection('insp-legacy')['spec_text'] == s.spec_text
    assert store.correction('correction-legacy')['spec_text'] == s.spec_text
    assert ('correction-legacy' in store.due_corrections()) == (sync_status == 'pending')
    with store.engine.connect() as c:
        row = c.execute(sa.select(db.inspections.c.owner_id, db.inspections.c.verdict)
                        .where(db.inspections.c.id == 'insp-legacy')).one()
        version = c.execute(sa.text('SELECT version_num FROM alembic_version')).scalar_one()
    assert tuple(row) == ('owner-a', 'good')
    assert version == '0003'


def test_render_postgres_urls_use_the_psycopg_driver():
    assert db.normalize_url('postgres://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
    assert db.normalize_url('postgresql://u:p@host/db') == 'postgresql+psycopg://u:p@host/db'
    assert db.as_url('/tmp/x.sqlite3') == 'sqlite:////tmp/x.sqlite3'
