"""Versioned factory repository. HTTP callers own role authorization.

Every mutation and its audit event commit together. SQLite serializes writes before
reading state; Postgres locks the team, then uses compare-and-swap record versions.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import re
import uuid

from fastapi import HTTPException
import sqlalchemy as sa

from .. import db
from . import tables
from .resolution import lot_resolution

KINDS = {'product', 'revision', 'station', 'lot', 'capture', 'review', 'standard',
         'nonconformance', 'event', 'validation', 'spec_reading'}
RESERVED = {'id', 'kind', 'owner_id', 'version', 'created_at', 'updated_at'}
IDENTIFIER = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def transaction(engine, owner_id=None):
    with engine.begin() as connection:
        if connection.dialect.name == 'sqlite':
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        elif owner_id:
            connection.execute(sa.select(tables.teams.c.id).where(
                tables.teams.c.id == owner_id).with_for_update()).first()
        yield connection


class PilotStore:
    def __init__(self, engine):
        self.engine = engine

    @staticmethod
    def _row(row):
        return {**deepcopy(row['payload']), **{key: row[key] for key in RESERVED}}

    def _get(self, connection, owner_id, id, kind=None):
        query = sa.select(tables.records).where(tables.records.c.owner_id == owner_id, tables.records.c.id == id)
        if kind is not None:
            query = query.where(tables.records.c.kind == kind)
        row = connection.execute(query).mappings().first()
        if row is None:
            raise HTTPException(404, 'Factory record not found.')
        return self._row(row)

    def get(self, owner_id, id, kind=None):
        with self.engine.connect() as connection:
            return self._get(connection, owner_id, id, kind)

    def _list(self, connection, owner_id, kind):
        query = sa.select(tables.records).where(tables.records.c.owner_id == owner_id, tables.records.c.kind == kind)
        return [self._row(row) for row in connection.execute(query.order_by(
            tables.records.c.created_at.desc(), tables.records.c.id.desc())).mappings()]

    def list(self, owner_id, kind):
        with self.engine.connect() as connection:
            return self._list(connection, owner_id, kind)

    def _insert(self, connection, owner_id, kind, fields, id=None):
        timestamp = now()
        record_id = id or f'{kind}-{uuid.uuid4().hex}'
        if not isinstance(record_id, str) or not IDENTIFIER.fullmatch(record_id):
            raise HTTPException(422, 'Record IDs use 1–64 letters, digits, underscores or hyphens.')
        row = dict(id=record_id, owner_id=owner_id, kind=kind, version=1,
                   created_at=timestamp, updated_at=timestamp, payload=deepcopy(fields))
        connection.execute(tables.records.insert().values(**row))
        return self._row(row)

    def _event(self, connection, owner_id, actor, action, target_id, details=None):
        return self._insert(connection, owner_id, 'event', {
            'actor': deepcopy(actor), 'action': action, 'target_id': target_id, 'details': deepcopy(details or {})})

    def event(self, owner_id, actor, action, target_id, details=None):
        with transaction(self.engine, owner_id) as connection:
            return self._event(connection, owner_id, actor, action, target_id, details)

    def _validate(self, connection, owner_id, kind, item, previous=None):
        references = {'product_id': 'product', 'revision_id': 'revision', 'station_id': 'station',
                      'lot_id': 'lot', 'capture_id': 'capture', 'retake_of': 'capture', 'resolved_by': 'capture'}
        for field, expected in references.items():
            if item.get(field) and not (kind == 'capture' and field == 'capture_id'):
                self._get(connection, owner_id, item[field], expected)
        if kind == 'capture' and not previous and item.get('lot_id'):
            lot = self._get(connection, owner_id, item['lot_id'], 'lot')
            if lot.get('status') != 'open':
                raise HTTPException(409, 'New captures require an open lot.')
        if kind == 'revision' and previous:
            if any(item.get(field) != previous.get(field) for field in ('product_id', 'spec_text', 'label')):
                raise HTTPException(409, 'Revision identity and specification text are immutable; create a replacement revision.')
            if previous.get('status') in {'approved', 'retired'} and any(
                item.get(field) != previous.get(field) for field in ('taxonomy', 'capture_instructions', 'approved_by', 'approved_at')):
                raise HTTPException(409, 'Published revision taxonomy and instructions are immutable.')
            if previous.get('status') == 'retired' and item.get('status') != 'retired':
                raise HTTPException(409, 'A retired revision cannot be reactivated.')
            allowed = {'draft': {'draft', 'approved', 'retired'}, 'approved': {'approved', 'retired'}, 'retired': {'retired'}}
            if item.get('status') not in allowed.get(previous.get('status'), set()):
                raise HTTPException(409, 'Invalid revision transition.')
        if kind == 'standard' and previous:
            if previous.get('status') in {'approved', 'retired'} and any(
                item.get(field) != previous.get(field) for field in (
                    'correction_id', 'inspection_id', 'revision_id', 'clause', 'rule_text', 'verdict', 'defect_type')):
                raise HTTPException(409, 'Published standards are immutable; propose a replacement.')
            if previous.get('status') == 'retired' and item.get('status') != 'retired':
                raise HTTPException(409, 'A retired standard cannot be reactivated.')
        if kind == 'lot':
            revision = self._get(connection, owner_id, item['revision_id'], 'revision') if item.get('revision_id') else None
            station = self._get(connection, owner_id, item['station_id'], 'station') if item.get('station_id') else None
            if revision and station and station.get('product_id') != revision.get('product_id'):
                raise HTTPException(422, 'Station and revision must belong to the same product.')
            if not previous and ((revision and revision.get('status') != 'approved') or (station and not station.get('active'))):
                raise HTTPException(409, 'An open lot requires an approved revision and active station.')
            if previous and any(item.get(field) != previous.get(field) for field in ('revision_id', 'station_id')):
                raise HTTPException(409, 'Lot revision and capture station are immutable.')
            if item.get('status') == 'closed' and (not previous or previous.get('status') != 'closed'):
                self._check_lot_closure(connection, owner_id, item.get('id'))

    def _check_lot_closure(self, connection, owner_id, lot_id):
        captures = [item for item in self._list(connection, owner_id, 'capture') if item.get('lot_id') == lot_id]
        reviews = [item for item in self._list(connection, owner_id, 'review') if item.get('lot_id') == lot_id]
        inspection_ids = {item['inspection_id'] for item in captures if item.get('inspection_id')}
        inspections = {row['id']: row['payload'] for row in connection.execute(sa.select(
            db.inspections.c.id, db.inspections.c.payload).where(
                db.inspections.c.owner_id == owner_id, db.inspections.c.id.in_(inspection_ids))).mappings()}
        state = lot_resolution(captures, reviews, inspections)
        if state['pending_capture_ids']:
            raise HTTPException(409, 'Resolve pending, failed or quarantined captures before closing the lot.')
        if state['pending_review_ids']:
            raise HTTPException(409, 'Resolve open or quarantined human reviews before closing the lot.')
        if state['unresolved_parts']:
            raise HTTPException(409, 'Hold and retake dispositions leave physical items unresolved.')

    def create(self, owner_id, kind, fields, actor=None, id=None):
        if kind not in KINDS or RESERVED.intersection(fields):
            raise HTTPException(422, 'Invalid record kind or server-controlled fields.')
        fields = deepcopy(fields)
        for key, value in {'revision': ('status', 'draft'), 'station': ('active', True),
                           'lot': ('status', 'open'), 'review': ('status', 'open'),
                           'standard': ('status', 'candidate'), 'nonconformance': ('status', 'open')}.items():
            if kind == key:
                fields.setdefault(*value)
        try:
            with transaction(self.engine, owner_id) as connection:
                self._validate(connection, owner_id, kind, fields)
                result = self._insert(connection, owner_id, kind, fields, id)
                if kind != 'event':
                    self._event(connection, owner_id, actor, f'{kind}.created', result['id'])
                return result
        except sa.exc.IntegrityError:
            raise HTTPException(409, 'A record with that identity already exists.') from None

    def update(self, owner_id, id, version, changes, actor=None):
        with transaction(self.engine, owner_id) as connection:
            return self._update(connection, owner_id, id, version, changes, actor)

    def _update(self, connection, owner_id, id, version, changes, actor=None):
        if RESERVED.intersection(changes):
            raise HTTPException(422, 'Record metadata is server controlled.')
        previous = self._get(connection, owner_id, id)
        if previous['kind'] in {'event', 'validation'}:
            raise HTTPException(409, 'Audit events and validation manifests are immutable.')
        if previous['version'] != version:
            raise HTTPException(409, 'This record changed. Reload it before saving.')
        item = {**previous, **deepcopy(changes)}
        self._validate(connection, owner_id, previous['kind'], item, previous)
        payload = {key: value for key, value in item.items() if key not in RESERVED}
        timestamp = now()
        changed = connection.execute(tables.records.update().where(
            tables.records.c.owner_id == owner_id, tables.records.c.id == id,
            tables.records.c.version == version).values(payload=payload, version=version + 1, updated_at=timestamp))
        if changed.rowcount != 1:
            raise HTTPException(409, 'This record changed. Reload it before saving.')
        self._event(connection, owner_id, actor, f'{previous["kind"]}.updated', id, {
            'fields': sorted(changes), 'previous_status': previous.get('status'), 'status': item.get('status')})
        return {**item, 'version': version + 1, 'updated_at': timestamp}

    def fail_capture(self, connection, owner_id, capture_id, message):
        query = sa.select(tables.records).where(tables.records.c.owner_id == owner_id,
            tables.records.c.id == capture_id, tables.records.c.kind == 'capture')
        if connection.dialect.name == 'postgresql':
            query = query.with_for_update()
        row = connection.execute(query).mappings().first()
        if row is None:
            return
        record = self._row(row)
        if not record.get('inspection_id') and record.get('status') != 'failed':
            self._update(connection, owner_id, capture_id, record['version'],
                {'status': 'failed', 'error': message[:500]}, record.get('context', {}).get('actor'))

    def delete_records(self, owner_id):
        with transaction(self.engine, owner_id) as connection:
            return connection.execute(tables.records.delete().where(tables.records.c.owner_id == owner_id)).rowcount

    def capture_context(self, owner_id, actor, *, revision_id, lot_id, station_id,
                        physical_part_id, capture_id, retake_of=None):
        if not isinstance(physical_part_id, str) or not physical_part_id.strip() or len(physical_part_id) > 100:
            raise HTTPException(422, 'Enter a physical part identifier of up to 100 characters.')
        if not isinstance(capture_id, str) or not IDENTIFIER.fullmatch(capture_id):
            raise HTTPException(422, 'Enter a capture ID of up to 64 letters, digits, underscores or hyphens.')
        with self.engine.connect() as connection:
            revision = self._get(connection, owner_id, revision_id, 'revision')
            product = self._get(connection, owner_id, revision['product_id'], 'product')
            station = self._get(connection, owner_id, station_id, 'station')
            lot = self._get(connection, owner_id, lot_id, 'lot')
            if revision.get('status') != 'approved' or lot.get('status') != 'open' or not station.get('active'):
                raise HTTPException(409, 'Captures require an approved revision, open lot and active station.')
            if (lot.get('revision_id') != revision_id or lot.get('station_id') != station_id or
                    station.get('product_id') != product['id']):
                raise HTTPException(422, 'The lot, product revision and capture station do not match.')
            if retake_of:
                original = self._get(connection, owner_id, retake_of, 'capture')
                if any(original.get(field) != value for field, value in (
                        ('lot_id', lot_id), ('revision_id', revision_id), ('physical_part_id', physical_part_id))):
                    raise HTTPException(422, 'A retake must refer to the same physical part, lot and revision.')
                if retake_of == capture_id:
                    raise HTTPException(422, 'A capture cannot be its own retake.')
            standards = {item['id']: item['version'] for item in self._list(connection, owner_id, 'standard')
                         if item.get('status') == 'approved' and item.get('revision_id') == revision_id}
        capture_instructions = revision.get('capture_instructions', '')
        instructions = '\n'.join(text for text in (capture_instructions, station.get('instructions', '')) if text)
        return deepcopy({
            'spec_text': revision['spec_text'], 'taxonomy': revision['taxonomy'], 'factory': product['factory'],
            'part_family': product['name'], 'product_id': product['id'], 'revision_id': revision_id,
            'revision_version': revision['version'], 'station_version': station['version'],
            'lot_id': lot_id, 'station_id': station_id, 'physical_part_id': physical_part_id.strip(),
            'capture_id': capture_id, 'retake_of': retake_of, 'actor': actor,
            'capture_instructions': capture_instructions, 'station_instructions': station.get('instructions', ''),
            'instructions': instructions, 'approved_source_versions': standards, 'captured_at': now()})
