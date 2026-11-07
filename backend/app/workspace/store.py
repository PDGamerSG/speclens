"""Durable application records. Hindsight remains the source of recalled memory."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Scope:
    factory: str
    part_family: str
    spec_text: str

    def __post_init__(self):
        for field in ('factory', 'part_family', 'spec_text'):
            value = getattr(self, field).strip()
            if not value:
                raise ValueError(f'{field} cannot be empty.')
            object.__setattr__(self, field, value)

    @property
    def id(self) -> str:
        data = json.dumps([self.factory.casefold(), self.part_family.casefold(), self.spec_text], ensure_ascii=False)
        return hashlib.sha256(data.encode()).hexdigest()[:24]

    @property
    def bank_id(self) -> str:
        return f'speclens-{self.id}'


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.executescript('''
                CREATE TABLE IF NOT EXISTS inspections (
                    id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS inspections_scope ON inspections(scope_id, created_at);
                CREATE TABLE IF NOT EXISTS corrections (
                    id TEXT PRIMARY KEY, inspection_id TEXT UNIQUE NOT NULL,
                    scope_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL,
                    FOREIGN KEY(inspection_id) REFERENCES inspections(id)
                );
                CREATE INDEX IF NOT EXISTS corrections_scope ON corrections(scope_id, created_at);
                CREATE TABLE IF NOT EXISTS comparisons (
                    id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_inspection(self, item: dict) -> dict:
        item = {**item, 'created_at': item.get('created_at') or now()}
        with self.connection() as db:
            db.execute('INSERT INTO inspections VALUES (?, ?, ?, ?)',
                       (item['id'], item['scope_id'], item['created_at'], json.dumps(item)))
        return item

    def inspection(self, id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute('SELECT payload FROM inspections WHERE id=?', (id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def inspections(self, scope_id: str, limit: int | None = None) -> list[dict]:
        with self.connection() as db:
            query = 'SELECT payload FROM inspections WHERE scope_id=? ORDER BY created_at DESC'
            params = (scope_id,) if limit is None else (scope_id, limit)
            rows = db.execute(query if limit is None else query + ' LIMIT ?', params).fetchall()
        return [json.loads(r['payload']) for r in rows]

    def add_correction(self, inspection_id: str, *, verdict: str, defect_type: str, rule_text: str, reviewer: str) -> dict:
        original = self.inspection(inspection_id)
        if original is None:
            raise KeyError('Inspection not found.')
        item = {'id': f'correction-{uuid.uuid4().hex}', 'inspection_id': inspection_id,
                'scope_id': original['scope_id'], 'factory': original['factory'],
                'part_family': original['part_family'], 'spec_text': original['spec_text'],
                'original_verdict': original['verdict'], 'original_type': original['type'],
                'original_rationale': original['rationale'], 'image_url': original['image_url'],
                'source_kind': original.get('source_kind', 'unknown'), 'source_group': original.get('source_group'),
                'image_sha256': original['image_sha256'], 'verdict': verdict, 'defect_type': defect_type,
                'rule_text': rule_text.strip(), 'reviewer': reviewer.strip(), 'created_at': now(),
                'sync_status': 'pending', 'sync_error': None}
        try:
            with self.connection() as db:
                db.execute('INSERT INTO corrections VALUES (?, ?, ?, ?, ?)',
                           (item['id'], inspection_id, item['scope_id'], item['created_at'], json.dumps(item)))
        except sqlite3.IntegrityError:
            raise ValueError('This inspection already has a correction. Inspect another part to add a new rule.') from None
        return item

    def correction(self, id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute('SELECT payload FROM corrections WHERE id=?', (id,)).fetchone()
        return json.loads(row['payload']) if row else None

    def corrections(self, scope_id: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute('SELECT payload FROM corrections WHERE scope_id=? ORDER BY created_at DESC', (scope_id,)).fetchall()
        return [json.loads(r['payload']) for r in rows]

    def mark_sync(self, id: str, status: str, error: str | None = None) -> dict:
        with self.connection() as db:
            row = db.execute('SELECT payload FROM corrections WHERE id=?', (id,)).fetchone()
            if row is None:
                raise KeyError('Correction not found.')
            item = {**json.loads(row['payload']), 'sync_status': status, 'sync_error': error}
            db.execute('UPDATE corrections SET payload=? WHERE id=?', (json.dumps(item), id))
        return item

    def add_comparison(self, item: dict) -> dict:
        with self.connection() as db:
            db.execute('INSERT INTO comparisons VALUES (?, ?, ?, ?)',
                       (item['id'], item['scope_id'], item['created_at'], json.dumps(item)))
        return item

    def comparisons(self, scope_id: str) -> list[dict]:
        with self.connection() as db:
            rows = db.execute('SELECT payload FROM comparisons WHERE scope_id=? ORDER BY created_at DESC', (scope_id,)).fetchall()
        return [json.loads(r['payload']) for r in rows]
