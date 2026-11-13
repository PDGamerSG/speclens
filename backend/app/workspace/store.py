"""Durable application records. Hindsight remains the source of recalled memory.

Records keep their full JSON payload, so the API returns exactly what was saved. Columns such as verdict,
class, cost and owner are copies for queries, paging and the dashboard. Specification text is stored once in
spec_revisions; records carry its ID and get the text back when read.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa

from .. import db
from ..db import comparisons as comparisons_table
from ..db import corrections as corrections_table
from ..db import inspections as inspections_table
from ..db import spec_revisions


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def spec_revision_id(spec_text: str) -> str:
    return hashlib.sha256(spec_text.encode()).hexdigest()[:24]


@dataclass(frozen=True)
class Scope:
    factory: str
    part_family: str
    spec_text: str
    owner_id: str = ''

    def __post_init__(self):
        for field in ('factory', 'part_family', 'spec_text'):
            value = getattr(self, field).strip()
            if not value:
                raise ValueError(f'{field} cannot be empty.')
            object.__setattr__(self, field, value)

    @property
    def id(self) -> str:
        identity = [self.factory.casefold(), self.part_family.casefold(), self.spec_text]
        if self.owner_id:
            identity.append(self.owner_id)
        data = json.dumps(identity, ensure_ascii=False)
        return hashlib.sha256(data.encode()).hexdigest()[:24]

    @property
    def bank_id(self) -> str:
        return f'speclens-{self.id}'

    @property
    def spec_revision_id(self) -> str:
        return spec_revision_id(self.spec_text)


ARMS = ('baseline', 'with_memory')


class Store:
    def __init__(self, target: str | Path | None = None):
        self.engine = db.engine(target)
        self._specs: dict[str, str] = {}

    # Specification text ------------------------------------------------------------------------------------

    def save_spec(self, connection: sa.Connection, spec_text: str) -> str:
        sid = spec_revision_id(spec_text)
        if sid not in self._specs:
            db.upsert_ignore(connection, spec_revisions, {'id': sid, 'spec_text': spec_text, 'created_at': now()})
            self._specs[sid] = spec_text
        return sid

    def spec_text(self, sid: str) -> str | None:
        if sid not in self._specs:
            with self.engine.connect() as c:
                text = c.execute(sa.select(spec_revisions.c.spec_text).where(spec_revisions.c.id == sid)).scalar()
            if text is None:
                return None
            self._specs[sid] = text
        return self._specs[sid]

    def taxonomy(self, sid: str) -> dict | None:
        with self.engine.connect() as c:
            return c.execute(sa.select(spec_revisions.c.taxonomy).where(spec_revisions.c.id == sid)).scalar()

    def save_taxonomy(self, spec_text: str, taxonomy: dict) -> str:
        with self.engine.begin() as c:
            sid = self.save_spec(c, spec_text)
            c.execute(spec_revisions.update().where(spec_revisions.c.id == sid).values(taxonomy=taxonomy))
        return sid

    def _pack(self, connection: sa.Connection, item: dict) -> dict:
        item = dict(item)
        for arm in ARMS:
            if isinstance(item.get(arm), dict):
                item[arm] = self._pack(connection, item[arm])
        text = item.pop('spec_text', None)
        if isinstance(text, str):
            item['spec_revision_id'] = self.save_spec(connection, text)
        return item

    def _unpack(self, item: dict, with_spec: bool = True) -> dict:
        item = dict(item)
        for arm in ARMS:
            if isinstance(item.get(arm), dict):
                item[arm] = self._unpack(item[arm], with_spec)
        if not with_spec:
            item.pop('spec_text', None)
        elif 'spec_text' not in item and item.get('spec_revision_id'):
            item['spec_text'] = self.spec_text(item['spec_revision_id']) or ''
        return item

    # Inspections -------------------------------------------------------------------------------------------

    def add_inspection(self, item: dict) -> dict:
        item = {**item, 'created_at': item.get('created_at') or now()}
        with self.engine.begin() as c:
            packed = self._pack(c, item)
            c.execute(inspections_table.insert().values(
                id=item['id'], scope_id=item['scope_id'], created_at=item['created_at'], payload=packed,
                owner_id=item.get('owner_id', ''), verdict=item.get('verdict'), defect_type=item.get('type'),
                confidence=item.get('confidence'), cost_usd=item.get('cost_usd'),
                latency_ms=round(item['ms']) if isinstance(item.get('ms'), (int, float)) else None,
                memory_enabled=item.get('memory_enabled'), cited_memories=len(item.get('memories') or []),
                spec_revision_id=packed.get('spec_revision_id')))
        return item

    def inspection(self, id: str) -> dict | None:
        with self.engine.connect() as c:
            payload = c.execute(sa.select(inspections_table.c.payload).where(inspections_table.c.id == id)).scalar()
        return self._unpack(payload) if payload is not None else None

    def update_inspection(self, id: str, **values) -> dict:
        with self.engine.begin() as c:
            payload = c.execute(sa.select(inspections_table.c.payload).where(inspections_table.c.id == id)).scalar()
            if payload is None:
                raise KeyError('Inspection not found.')
            packed = {**payload, **values}
            c.execute(inspections_table.update().where(inspections_table.c.id == id).values(payload=packed))
        return self._unpack(packed)

    def inspections(self, scope_id: str, limit: int | None = None, before: str | None = None,
                    with_spec: bool = True) -> list[dict]:
        query = sa.select(inspections_table.c.payload).where(inspections_table.c.scope_id == scope_id)
        if before:
            query = query.where(inspections_table.c.created_at < before)
        query = query.order_by(inspections_table.c.created_at.desc(), inspections_table.c.id.desc())
        if limit is not None:
            query = query.limit(limit)
        with self.engine.connect() as c:
            return [self._unpack(p, with_spec) for p in c.execute(query).scalars()]

    def count_inspections(self, scope_id: str) -> int:
        with self.engine.connect() as c:
            return c.execute(sa.select(sa.func.count()).select_from(inspections_table)
                             .where(inspections_table.c.scope_id == scope_id)).scalar_one()

    # Corrections -------------------------------------------------------------------------------------------

    def add_correction(self, inspection_id: str, *, verdict: str, defect_type: str, rule_text: str, reviewer: str,
                       **extra) -> dict:
        original = self.inspection(inspection_id)
        if original is None:
            raise KeyError('Inspection not found.')
        item = {'id': f'correction-{uuid.uuid4().hex}', 'inspection_id': inspection_id,
                'owner_id': original.get('owner_id', ''),
                'scope_id': original['scope_id'], 'factory': original['factory'],
                'part_family': original['part_family'], 'spec_text': original['spec_text'],
                'original_verdict': original['verdict'], 'original_type': original['type'],
                'original_rationale': original['rationale'], 'image_url': original['image_url'],
                'source_kind': original.get('source_kind', 'unknown'), 'source_group': original.get('source_group'),
                'image_sha256': original['image_sha256'], 'verdict': verdict, 'defect_type': defect_type,
                'rule_text': rule_text.strip(), 'reviewer': reviewer.strip(), 'created_at': now(),
                'sync_status': 'pending', 'sync_error': None, **extra}
        try:
            with self.engine.begin() as c:
                c.execute(corrections_table.insert().values(
                    id=item['id'], inspection_id=inspection_id, scope_id=item['scope_id'],
                    created_at=item['created_at'], payload=self._pack(c, item), owner_id=item['owner_id'],
                    verdict=verdict, defect_type=defect_type, sync_status='pending', next_sync_at=time.time()))
        except sa.exc.IntegrityError:
            raise ValueError('This inspection already has a correction. Inspect another part to add a new rule.') from None
        return item

    def correction(self, id: str) -> dict | None:
        with self.engine.connect() as c:
            payload = c.execute(sa.select(corrections_table.c.payload).where(corrections_table.c.id == id)).scalar()
        return self._unpack(payload) if payload is not None else None

    def corrections(self, scope_id: str, with_spec: bool = True) -> list[dict]:
        query = (sa.select(corrections_table.c.payload).where(corrections_table.c.scope_id == scope_id)
                 .order_by(corrections_table.c.created_at.desc()))
        with self.engine.connect() as c:
            return [self._unpack(p, with_spec) for p in c.execute(query).scalars()]

    def mark_sync(self, id: str, status: str, error: str | None = None, retry_in: float | None = None) -> dict:
        """Record a sync outcome. A synced correction never goes back to pending, even if a late retry fails."""
        table = corrections_table
        with self.engine.begin() as c:
            query = sa.select(table.c.payload, table.c.sync_status, table.c.sync_attempts).where(table.c.id == id)
            if c.dialect.name == 'postgresql':
                query = query.with_for_update()
            row = c.execute(query).first()
            if row is None:
                raise KeyError('Correction not found.')
            if row.sync_status == 'synced':
                return self._unpack(row.payload)
            item = {**row.payload, 'sync_status': status, 'sync_error': error}
            attempts = row.sync_attempts + (status != 'synced')
            changed = c.execute(table.update().where(table.c.id == id, table.c.sync_status != 'synced').values(
                payload=item, sync_status=status, sync_attempts=attempts,
                next_sync_at=None if status == 'synced' else time.time() + (retry_in or 0)))
            if changed.rowcount == 0:
                item = c.execute(sa.select(table.c.payload).where(table.c.id == id)).scalar_one()
        return self._unpack(item)

    def due_corrections(self, limit: int = 20) -> list[str]:
        """Pending corrections whose next memory sync attempt is due: the outbox the worker drains."""
        table = corrections_table
        query = (sa.select(table.c.id).where(table.c.sync_status != 'synced', table.c.next_sync_at <= time.time())
                 .order_by(table.c.next_sync_at).limit(limit))
        with self.engine.connect() as c:
            return list(c.execute(query).scalars())

    def sync_attempts(self, id: str) -> int:
        with self.engine.connect() as c:
            return c.execute(sa.select(corrections_table.c.sync_attempts)
                             .where(corrections_table.c.id == id)).scalar() or 0

    # Comparisons -------------------------------------------------------------------------------------------

    def add_comparison(self, item: dict) -> dict:
        owner = (item.get('baseline') or {}).get('owner_id', '')
        with self.engine.begin() as c:
            c.execute(comparisons_table.insert().values(
                id=item['id'], scope_id=item['scope_id'], created_at=item['created_at'],
                payload=self._pack(c, item), owner_id=owner))
        return item

    def comparisons(self, scope_id: str, limit: int | None = None, with_spec: bool = True) -> list[dict]:
        query = (sa.select(comparisons_table.c.payload).where(comparisons_table.c.scope_id == scope_id)
                 .order_by(comparisons_table.c.created_at.desc()))
        if limit is not None:
            query = query.limit(limit)
        with self.engine.connect() as c:
            return [self._unpack(p, with_spec) for p in c.execute(query).scalars()]

    def count_comparisons(self, scope_id: str) -> int:
        with self.engine.connect() as c:
            return c.execute(sa.select(sa.func.count()).select_from(comparisons_table)
                             .where(comparisons_table.c.scope_id == scope_id)).scalar_one()

    # Retention, export and deletion ------------------------------------------------------------------------

    def export_owner(self, owner_id: str) -> dict:
        """Every record that belongs to one owner, with its specification text."""
        out = {}
        for name, table in (('inspections', inspections_table), ('corrections', corrections_table),
                            ('comparisons', comparisons_table)):
            query = sa.select(table.c.payload).where(table.c.owner_id == owner_id).order_by(table.c.created_at)
            with self.engine.connect() as c:
                out[name] = [self._unpack(p) for p in c.execute(query).scalars()]
        return out

    def _delete_where(self, inspection_filter, correction_filter, comparison_filter, job_filter) -> dict:
        """Delete matching records in one transaction. Returns what callers must also remove elsewhere."""
        i, k, m, j = inspections_table, corrections_table, comparisons_table, db.jobs
        with self.engine.begin() as c:
            inspection_ids = list(c.execute(sa.select(i.c.id).where(inspection_filter)).scalars())
            removed_corrections = c.execute(sa.select(k.c.id, k.c.scope_id, k.c.sync_status).where(
                sa.or_(correction_filter, k.c.inspection_id.in_(inspection_ids)))).all()
            scope_ids = set(c.execute(sa.select(i.c.scope_id).where(i.c.id.in_(inspection_ids))).scalars())
            uploads = [p.get('upload') for p in c.execute(sa.select(j.c.payload).where(job_filter)).scalars()]
            c.execute(k.delete().where(k.c.id.in_([r.id for r in removed_corrections])))
            comparisons = c.execute(m.delete().where(comparison_filter)).rowcount
            c.execute(i.delete().where(i.c.id.in_(inspection_ids)))
            jobs = c.execute(j.delete().where(job_filter)).rowcount
        media = [f'{id}{suffix}' for id in inspection_ids for suffix in ('.jpg', '_overlay.jpg', '_mask.png')]
        media += [f'{r.id}_crop.jpg' for r in removed_corrections]
        media += [u for u in uploads if u]
        return {'inspections': len(inspection_ids), 'corrections': len(removed_corrections), 'comparisons': comparisons,
                'jobs': jobs, 'media': media, 'scope_ids': sorted(scope_ids | {r.scope_id for r in removed_corrections}),
                'memories': [(f'speclens-{r.scope_id}', r.id) for r in removed_corrections if r.sync_status == 'synced']}

    def delete_owner(self, owner_id: str) -> dict:
        return self._delete_where(inspections_table.c.owner_id == owner_id, corrections_table.c.owner_id == owner_id,
                                  comparisons_table.c.owner_id == owner_id, db.jobs.c.owner_id == owner_id)

    def purge_before(self, cutoff: str, jobs_before: float) -> dict:
        """Records created before an ISO timestamp, and finished or abandoned jobs older than an epoch time."""
        return self._delete_where(inspections_table.c.created_at < cutoff, corrections_table.c.created_at < cutoff,
                                  comparisons_table.c.created_at < cutoff,
                                  sa.and_(db.jobs.c.updated_at < jobs_before, db.jobs.c.status.in_(('done', 'failed'))))
