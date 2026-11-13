"""Bind existing inspections to controlled records without changing their original assessment."""
from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException

from ..jobs.queue import JobFailed
from ..workspace.store import Scope, now
from .store import PilotStore


def optional(store: PilotStore, owner_id: str, id: str, kind: str) -> dict | None:
    try:
        return store.get(owner_id, id, kind)
    except HTTPException as error:
        if error.status_code != 404:
            raise
        return None


def eligible_sources(store, scope: Scope, snapshot: dict | None = None) -> dict:
    corrections = {c['id']: c for c in store.corrections(scope.id) if c['sync_status'] == 'synced'}
    if not scope.owner_id.startswith('team-'):
        return corrections
    catalog = PilotStore(store.engine)
    revision = optional(catalog, scope.owner_id, scope.revision_id, 'revision') if scope.revision_id else None
    if revision is None or revision.get('status') != 'approved':
        return {}
    standards = catalog.list(scope.owner_id, 'standard')
    result = {}
    for standard in standards:
        if standard.get('status') != 'approved' or standard.get('revision_id') != scope.revision_id:
            continue
        if snapshot is not None and snapshot.get(standard['id']) != standard['version']:
            continue
        cid = standard.get('correction_id')
        if cid in corrections:
            result[cid] = {**corrections[cid], 'standard_id': standard['id'], 'standard_version': standard['version']}
    return result


def evaluation_policy(store, scope: Scope) -> dict:
    catalog = PilotStore(store.engine)
    if not scope.revision_id:
        raise JobFailed(422, 'Select an approved factory revision for this comparison.')
    revision = catalog.get(scope.owner_id, scope.revision_id, 'revision')
    if revision.get('status') != 'approved':
        raise JobFailed(409, 'This revision is not approved for a new comparison.')
    return {'revision_id': revision['id'], 'revision_version': revision['version'],
            'taxonomy': revision['taxonomy'], 'spec_text': revision['spec_text'],
            'approved_source_versions': {s['id']: s['version'] for s in catalog.list(scope.owner_id, 'standard')
                if s.get('status') == 'approved' and s.get('revision_id') == revision['id']},
            'snapshot_at': now()}


def validate_snapshot(store, scope: Scope, context: dict, *, memory: bool) -> list[str]:
    pilot = PilotStore(store.engine)
    invalid = []
    for kind, id_key, version_key, valid_key, valid_value in (
        ('revision', 'revision_id', 'revision_version', 'status', 'approved'),
        ('station', 'station_id', 'station_version', 'active', True),
    ):
        if not context.get(id_key):
            continue
        record = optional(pilot, scope.owner_id, context[id_key], kind)
        if (record is None or record.get(valid_key) != valid_value
                or record['version'] != context.get(version_key)):
            invalid.append(kind)
    if memory:
        for sid, version in context.get('approved_source_versions', {}).items():
            record = optional(pilot, scope.owner_id, sid, 'standard')
            if record is None or record.get('status') != 'approved' or record['version'] != version:
                invalid.append(sid)
    return invalid


def reserve_capture(store, scope: Scope, context: dict, data: bytes, *, memory: bool) -> tuple[str, dict | None, dict]:
    """Bind a submission key to its input; a retry cannot change the image or its context."""
    if context.get('revision_id') != scope.revision_id or not scope.owner_id.startswith('team-'):
        raise JobFailed(422, 'The capture does not match this controlled revision.')
    pilot = PilotStore(store.engine)
    capture_id = context['capture_id']
    signature = hashlib.sha256(json.dumps({
        'scope': scope.id, 'photo': hashlib.sha256(data).hexdigest(), 'memory': memory,
        'lot': context['lot_id'], 'station': context['station_id'], 'part': context['physical_part_id'],
        'retake_of': context.get('retake_of'),
        'revision_version': context.get('revision_version'), 'station_version': context.get('station_version'),
        'approved_source_versions': context.get('approved_source_versions', {}) if memory else {},
    }, sort_keys=True).encode()).hexdigest()
    saved = optional(pilot, scope.owner_id, capture_id, 'capture')
    if saved is not None and saved.get('signature') != signature:
        raise JobFailed(409, 'This capture ID was reused for different photo or part details. Start a new capture.')
    if saved is not None:
        context = saved['context']
    result_id = 'insp-' + hashlib.sha256(f'{scope.owner_id}:{capture_id}'.encode()).hexdigest()[:24]
    existing = store.inspection(result_id)
    if existing is not None:
        if existing.get('owner_id') != scope.owner_id:
            raise JobFailed(409, 'This capture could not be matched to its owner.')
        complete_capture(store, existing)
        return result_id, existing, context
    if validate_snapshot(store, scope, context, memory=memory):
        raise JobFailed(409, 'The inspection recipe changed or was withdrawn. Select an approved revision and try again.')
    lot = pilot.get(scope.owner_id, context['lot_id'], 'lot')
    if lot.get('status') != 'open':
        raise JobFailed(409, 'This lot is closed. Open a lot before capturing another part.')
    if saved is None:
        fields = {**{k: v for k, v in context.items() if k != 'owner_id'}, 'context': context,
                  'signature': signature, 'status': 'pending', 'inspection_id': None}
        try:
            pilot.create(scope.owner_id, 'capture', fields, actor=context['actor'], id=capture_id)
        except HTTPException as error:
            if error.status_code != 409:
                raise
            current = pilot.get(scope.owner_id, capture_id, 'capture')
            if current.get('signature') != signature:
                raise JobFailed(409, 'This capture ID was reused for different photo or part details.') from None
            context = current['context']
    return result_id, None, context


def complete_capture(store, inspection: dict) -> None:
    context = inspection.get('pilot')
    if not context:
        return
    pilot, team = PilotStore(store.engine), inspection['owner_id']
    review_id = 'review-' + inspection['id'].removeprefix('insp-')
    if optional(pilot, team, review_id, 'review') is None:
        fields = {key: context[key] for key in (
            'product_id', 'revision_id', 'lot_id', 'station_id', 'physical_part_id', 'capture_id')}
        fields.update(inspection_id=inspection['id'], inspection=inspection, status='open', outcome=None,
                      reason='', assignee=None, quarantined=bool(context.get('quarantined')),
                      queue_reason='Recipe withdrawn during analysis' if context.get('quarantined') else
                          'Model requested review' if inspection['verdict'] == 'uncertain' else 'Pilot confirmation')
        try:
            pilot.create(team, 'review', fields, actor=context['actor'], id=review_id)
        except HTTPException as error:
            if error.status_code != 409:
                raise
    capture = pilot.get(team, context['capture_id'], 'capture')
    if capture.get('inspection_id') != inspection['id']:
        try:
            pilot.update(team, capture['id'], capture['version'], {
                'status': 'quarantined' if context.get('quarantined') else 'done',
                'inspection_id': inspection['id'], 'completed_at': now(),
            }, actor=context['actor'])
        except HTTPException as error:
            if error.status_code != 409:
                raise
            current = pilot.get(team, capture['id'], 'capture')
            if current.get('inspection_id') != inspection['id']:
                raise
    if context.get('retake_of') and not context.get('quarantined'):
        prior_id = context['retake_of']
        prior = pilot.get(team, prior_id, 'capture')
        # Preserve prior status and review; link the completed replacement explicitly.
        if prior.get('resolved_by') != capture['id']:
            pilot.update(team, prior['id'], prior['version'], {'resolved_by': capture['id']}, actor=context['actor'])
        for review in pilot.list(team, 'review'):
            if review.get('capture_id') == prior_id and review.get('resolved_by') != capture['id']:
                pilot.update(team, review['id'], review['version'], {'resolved_by': capture['id']}, actor=context['actor'])


def propose_standard(store, inspection: dict, correction: dict) -> dict:
    context = inspection['pilot']
    pilot = PilotStore(store.engine)
    id = 'standard-' + correction['id'].removeprefix('correction-')
    existing = optional(pilot, inspection['owner_id'], id, 'standard')
    if existing is not None:
        return existing
    taxonomy = context['taxonomy']
    clause = next((c.get('clause', '') for c in taxonomy['classes']
                   if c['defect_type'] == correction['defect_type']), '')
    fields = {
        'correction_id': correction['id'], 'inspection_id': inspection['id'],
        'revision_id': context['revision_id'], 'product_id': context['product_id'],
        'rule_text': correction['rule_text'], 'verdict': correction['verdict'],
        'defect_type': correction['defect_type'], 'clause': clause, 'status': 'candidate',
        'reviewer': correction['reviewer'], 'image_url': inspection['image_url'],
        'crop_url': correction.get('crop_url'), 'approver': None,
    }
    try:
        return pilot.create(inspection['owner_id'], 'standard', fields,
                            actor=correction.get('actor') or context['actor'], id=id)
    except HTTPException as error:
        if error.status_code != 409:
            raise
        return pilot.get(inspection['owner_id'], id, 'standard')


def correction_approved(store, correction: dict) -> bool:
    if not correction.get('owner_id', '').startswith('team-'):
        return True
    return any(s.get('correction_id') == correction['id'] and s.get('status') == 'approved'
               for s in PilotStore(store.engine).list(correction['owner_id'], 'standard'))
