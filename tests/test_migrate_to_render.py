"""The Lightsail data can be copied into the Render stores, the source file stays untouched, and a rerun adds nothing."""
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

from app.workspace.store import Store

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'migrate_to_render.py'


def load():
    spec = importlib.util.spec_from_file_location('migrate_to_render', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_var(tmp_path):
    var = tmp_path / 'var'
    (var / 'workspace').mkdir(parents=True)
    (var / 'workspace' / 'insp-legacy0000000001.jpg').write_bytes(b'photo')
    (var / 'ledger.jsonl').write_text(json.dumps({'model': 'muse-spark-1.3', 'op': 'inspect', 'cost_usd': 0.0035}) + '\n')
    record = {'id': 'insp-legacy0000000001', 'scope_id': 'scope-1', 'owner_id': 'o', 'spec_text': 'Reject ink.',
              'verdict': 'good', 'type': 'good', 'created_at': '2026-11-07T12:00:00+00:00'}
    legacy = sqlite3.connect(var / 'speclens.sqlite3')
    legacy.executescript('''
        CREATE TABLE inspections (id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE corrections (id TEXT PRIMARY KEY, inspection_id TEXT UNIQUE NOT NULL, scope_id TEXT NOT NULL,
            created_at TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE comparisons (id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
    ''')
    legacy.execute('INSERT INTO inspections VALUES (?, ?, ?, ?)',
                   (record['id'], record['scope_id'], record['created_at'], json.dumps(record)))
    legacy.commit()
    legacy.close()
    return var


def test_lightsail_data_moves_to_the_new_stores_and_a_rerun_adds_nothing(tmp_path):
    var = legacy_var(tmp_path)
    before = hashlib.sha256((var / 'speclens.sqlite3').read_bytes()).hexdigest()
    target = f'sqlite:///{tmp_path / "render.sqlite3"}'
    media = tmp_path / 'r2'
    summary = load().main(['--var', str(var), '--target', target, '--media-target', str(media)])
    assert summary['inspections'] == 1
    assert summary['spec_revisions'] == 1
    assert summary['model_calls'] == 1
    assert summary['media_files'] == 1
    assert (media / 'insp-legacy0000000001.jpg').read_bytes() == b'photo'
    assert Store(target).inspection('insp-legacy0000000001')['spec_text'] == 'Reject ink.'
    assert hashlib.sha256((var / 'speclens.sqlite3').read_bytes()).hexdigest() == before, 'the source is never changed'
    again = load().main(['--var', str(var), '--target', target, '--media-target', str(media)])
    assert again['inspections'] == 0 and again['model_calls'] == 0
