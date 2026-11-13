"""Complete lot evidence, with part-level decisions separated from capture attempts."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import defaultdict

from fastapi import APIRouter, Request, Response
import sqlalchemy as sa

from .. import db
from ..workspace.store import now
from .auth import require_identity
from .store import PilotStore
from .resolution import lot_resolution

router = APIRouter(prefix='/api/workspace/pilot', tags=['Factory reports'])


def safe_csv(value):
    text = '' if value is None else str(value)
    return "'" + text if text.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else text


def lot_evidence(service, owner_id: str, lot_id: str) -> dict:
    store = PilotStore(service.store.engine)
    lot = store.get(owner_id, lot_id, 'lot')
    revision = store.get(owner_id, lot['revision_id'], 'revision')
    product = store.get(owner_id, revision['product_id'], 'product')
    station = store.get(owner_id, lot['station_id'], 'station')
    captures = sorted((c for c in store.list(owner_id, 'capture') if c['lot_id'] == lot_id),
                      key=lambda c: (c['created_at'], c['id']))
    reviews = sorted((r for r in store.list(owner_id, 'review') if r['lot_id'] == lot_id),
                     key=lambda r: (r['created_at'], r['id']))
    inspection_ids = {c['inspection_id'] for c in captures if c.get('inspection_id')}
    inspections = [service.store.inspection(id) for id in sorted(inspection_ids)]
    inspections = [i for i in inspections if i and i.get('owner_id') == owner_id]
    # No overview page limit: select the complete scoped correction set for these inspections.
    with service.store.engine.connect() as connection:
        corrections = [service.store._unpack(p) for p in connection.execute(
            sa.select(db.corrections.c.payload).where(db.corrections.c.owner_id == owner_id,
                db.corrections.c.inspection_id.in_(inspection_ids))).scalars()]
    standards = [s for s in store.list(owner_id, 'standard') if s.get('revision_id') == revision['id']]
    issues = [n for n in store.list(owner_id, 'nonconformance') if n.get('lot_id') == lot_id]
    targets = {lot_id, product['id'], revision['id'], station['id'],
               *(c['id'] for c in captures), *(r['id'] for r in reviews),
               *(s['id'] for s in standards), *(n['id'] for n in issues)}
    activity = [e for e in store.list(owner_id, 'event') if e.get('target_id') in targets]
    evidence = []
    for record in [*inspections, *corrections]:
        for field in ('image_url', 'mask_url', 'overlay_url', 'crop_url'):
            url = record.get(field)
            if not url:
                continue
            available = None
            digest = None
            if url.startswith('/files/workspace/'):
                content = service.media.get(url.removeprefix('/files/workspace/'))
                available = content is not None
                digest = hashlib.sha256(content).hexdigest() if content is not None else None
            evidence.append({'record_id': record['id'], 'field': field, 'url': url,
                             'available': available, 'sha256': digest})
    by_part = defaultdict(list)
    for capture in captures:
        by_part[capture['physical_part_id']].append(capture)
    resolution = lot_resolution(captures, reviews, {i['id']: i for i in inspections})
    return {
        'format_version': 2, 'exported_at': now(), 'owner_id': owner_id,
        'lot': lot, 'product': product, 'revision': revision, 'station': station,
        'counts': {'physical_parts': len(by_part), 'capture_attempts': len(captures),
                   'assessments': len(inspections), 'reviews': len(reviews), 'unresolved_parts': resolution['unresolved_parts'],
                   'missing_evidence': sum(e['available'] is False for e in evidence)},
        'captures': captures, 'inspections': inspections, 'reviews': reviews, 'corrections': corrections,
        'standards': standards, 'nonconformances': issues, 'activity': activity, 'evidence': evidence,
        'part_resolution': resolution['parts'],
        'interpretation': {
            'model_result': 'An AI assessment, separate from the human disposition and material release.',
            'counts': 'Retakes count as attempts; each lot-scoped physical_part_id counts as one physical part.',
            'first_attempts': {part: attempts[0]['id'] for part, attempts in by_part.items()},
            'media': 'Image bytes are not embedded. Authenticated URLs and hashes identify retained media; missing files are explicit.',
            'reproducibility': 'Provider model aliases and stochastic outputs may not be exactly reproducible.',
        },
    }


def _load(request, id):
    from ..workspace.routes import service
    identity = require_identity(request)
    return lot_evidence(service, identity['team']['id'], id)


@router.get('/lots/{id}/export')
def export_lot(id: str, request: Request):
    data = _load(request, id)
    return Response(json.dumps(data, ensure_ascii=False), media_type='application/json',
                    headers={'Content-Disposition': f'attachment; filename="speclens-{id}.json"', 'Cache-Control': 'no-store'})


@router.get('/lots/{id}/csv')
def export_lot_csv(id: str, request: Request):
    data = _load(request, id)
    inspections = {i['id']: i for i in data['inspections']}
    reviews = {r['capture_id']: r for r in data['reviews']}
    out = io.StringIO()
    fields = ['lot_reference', 'physical_part_id', 'capture_id', 'retake_of', 'capture_status', 'inspection_id',
              'model_verdict', 'human_outcome', 'review_status', 'reviewer', 'reason', 'quarantined',
              'revision_id', 'station_id', 'captured_at', 'image_url']
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for capture in data['captures']:
        inspection = inspections.get(capture.get('inspection_id'), {})
        review = reviews.get(capture['id'], {})
        row = {'lot_reference': data['lot']['reference'], 'physical_part_id': capture['physical_part_id'],
               'capture_id': capture['id'], 'retake_of': capture.get('retake_of'), 'capture_status': capture.get('status'),
               'inspection_id': capture.get('inspection_id'), 'model_verdict': inspection.get('verdict'),
               'human_outcome': review.get('outcome'), 'review_status': review.get('status'),
               'reviewer': (review.get('reviewer') or {}).get('name'), 'reason': review.get('reason'),
               'quarantined': review.get('quarantined', False), 'revision_id': capture['revision_id'],
               'station_id': capture['station_id'], 'captured_at': capture.get('captured_at') or capture['created_at'],
               'image_url': inspection.get('image_url')}
        writer.writerow({key: safe_csv(value) for key, value in row.items()})
    return Response(out.getvalue(), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="speclens-{id}.csv"', 'Cache-Control': 'no-store'})
