"""Authenticated factory workspace API. Model calls remain in the inspection service."""
from __future__ import annotations

import math
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
import sqlalchemy as sa

from .. import db
from . import auth, tables
from .store import PilotStore, now

router = APIRouter(prefix='/api/workspace/pilot', tags=['factory workspace'],
                   dependencies=[Depends(auth.check_origin), Depends(auth.private_response)])
Role = Literal['admin', 'engineer', 'operator', 'viewer']
EDIT = {'admin', 'engineer'}


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')

    @field_validator('*', mode='before')
    @classmethod
    def trim_text(cls, value, info):
        return value.strip() if isinstance(value, str) and info.field_name not in {'password', 'token'} else value


class Account(Input):
    username: str = Field(min_length=3, max_length=64, pattern=r'^[A-Za-z0-9_.-]+$')
    password: str = Field(min_length=12, max_length=256)
    name: str = Field(min_length=1, max_length=100)


class Register(Account):
    team_name: str = Field(min_length=1, max_length=100)


class Login(Input):
    username: str = Field(min_length=3, max_length=64, pattern=r'^[A-Za-z0-9_.-]+$')
    password: str = Field(min_length=1, max_length=256)


class Join(Account):
    token: str = Field(min_length=20, max_length=200)


class Invite(Input):
    role: Role


class Version(Input):
    version: int = Field(ge=1, strict=True)


class MemberUpdate(Version):
    role: Role
    active: bool = Field(strict=True)


class Product(Input):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=100)
    factory: str = Field(min_length=1, max_length=100)
    description: str = Field(default='', max_length=4000)


class Revision(Input):
    product_id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=64)
    spec_text: str = Field(min_length=1, max_length=12000)
    capture_instructions: str = Field(default='', max_length=4000)


class RevisionUpdate(Version):
    status: Literal['approved', 'retired']
    taxonomy: dict | None = None


class Station(Input):
    name: str = Field(min_length=1, max_length=100)
    product_id: str = Field(min_length=1, max_length=64)
    instructions: str = Field(min_length=1, max_length=4000)


class StationUpdate(Version):
    active: bool = Field(strict=True)
    instructions: str | None = Field(default=None, min_length=1, max_length=4000)


class Lot(Input):
    reference: str = Field(min_length=1, max_length=100)
    revision_id: str = Field(min_length=1, max_length=64)
    station_id: str = Field(min_length=1, max_length=64)
    notes: str = Field(default='', max_length=4000)


class LotUpdate(Version):
    status: Literal['open', 'closed']


class ReviewUpdate(Version):
    status: Literal['open', 'claimed', 'closed']
    outcome: Literal['accept', 'reject', 'hold', 'retake'] | None = None
    reason: str | None = Field(default=None, min_length=1, max_length=4000)


class StandardUpdate(Version):
    status: Literal['approved', 'retired']
    reason: str | None = Field(default=None, min_length=1, max_length=4000)


class Nonconformance(Input):
    title: str = Field(min_length=1, max_length=200)
    lot_id: str = Field(min_length=1, max_length=64)
    inspection_id: str | None = Field(default=None, min_length=1, max_length=64)
    severity: Literal['minor', 'major', 'critical']
    description: str = Field(min_length=1, max_length=4000)
    containment: str = Field(default='', max_length=4000)
    requirement: str = Field(default='', max_length=2000)
    root_cause: str = Field(default='', max_length=2000)
    evidence: str = Field(default='', max_length=2000)
    assignee: str | None = Field(default=None, min_length=1, max_length=64)


class NonconformanceUpdate(Version):
    status: Literal['open', 'contained', 'closed']
    containment: str | None = Field(default=None, min_length=1, max_length=4000)
    corrective_action: str | None = Field(default=None, min_length=1, max_length=4000)
    resolution: str | None = Field(default=None, min_length=1, max_length=4000)
    requirement: str | None = Field(default=None, max_length=2000)
    root_cause: str | None = Field(default=None, max_length=2000)
    evidence: str | None = Field(default=None, max_length=2000)
    assignee: str | None = Field(default=None, min_length=1, max_length=64)


def records():
    return PilotStore(auth.workspace_engine())


def access(request, roles=None):
    identity = auth.require_identity(request, roles)
    return identity, identity['team']['id'], auth.actor_for(identity)


@router.get('/session')
def session(request: Request):
    return auth.session_payload(auth.current_identity(request))


@router.post('/register', status_code=201)
def register(body: Register, request: Request, response: Response):
    auth.auth_limit(request, 'register', body.username)
    identity, token = auth.register_account(**body.model_dump())
    auth.set_session(response, request, token)
    return auth.session_payload(identity)


@router.post('/login')
def login(body: Login, request: Request, response: Response):
    auth.auth_limit(request, 'login', body.username)
    identity, token = auth.login_account(**body.model_dump())
    auth.set_session(response, request, token)
    return auth.session_payload(identity)


@router.post('/logout')
def logout(request: Request, response: Response):
    auth.logout_account(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path='/', httponly=True, samesite='strict')
    return auth.session_payload(None)


@router.get('/team')
def team(request: Request):
    identity = auth.require_identity(request, {'admin'})
    return auth.team_members(identity)


@router.post('/invites', status_code=201)
def invite(body: Invite, request: Request):
    identity = auth.require_identity(request, {'admin'})
    return auth.create_invite(identity, body.role)


@router.post('/join', status_code=201)
def join(body: Join, request: Request, response: Response):
    auth.auth_limit(request, 'join', body.username)
    identity, token = auth.join_account(**body.model_dump())
    auth.set_session(response, request, token)
    return auth.session_payload(identity)


@router.patch('/members/{id}')
def member(id: str, body: MemberUpdate, request: Request):
    identity = auth.require_identity(request, {'admin'})
    return auth.update_member(identity, id, **body.model_dump())


@router.get('/overview')
def overview(request: Request):
    _, owner, _ = access(request)
    store = records()
    kinds = {'products': 'product', 'revisions': 'revision', 'stations': 'station', 'lots': 'lot',
             'captures': 'capture', 'reviews': 'review', 'standards': 'standard',
             'nonconformances': 'nonconformance', 'activity': 'event'}
    result = {key: store.list(owner, kind) for key, kind in kinds.items()}
    # Sync is independent of approval. Report its current durable outbox state.
    with store.engine.connect() as connection:
        correction_states = {row.id: row.sync_status for row in connection.execute(sa.select(
            db.corrections.c.id, db.corrections.c.sync_status).where(db.corrections.c.owner_id == owner))}
    for standard in result['standards']:
        standard['sync_status'] = correction_states.get(standard.get('correction_id'), standard.get('sync_status', 'pending'))
    return result


@router.post('/products', status_code=201)
def product(body: Product, request: Request):
    _, owner, actor = access(request, EDIT)
    return records().create(owner, 'product', body.model_dump(), actor)


@router.post('/revisions', status_code=201)
def revision(body: Revision, request: Request):
    from ..workspace.spec import parse_spec
    _, owner, actor = access(request, EDIT)
    return records().create(owner, 'revision', {**body.model_dump(), 'taxonomy': parse_spec(body.spec_text),
                                               'taxonomy_confirmed': False, 'status': 'draft'}, actor)


def _validate_taxonomy(taxonomy):
    """Return the complete shape consumed by inspection and mask measurement."""
    if not isinstance(taxonomy, dict):
        raise HTTPException(422, 'Confirm a valid specification taxonomy.')

    def dimension(value, name, *, positive=False):
        if value is None:
            return None
        try:
            valid = (type(value) in {int, float} and math.isfinite(value)
                     and (value > 0 if positive else value >= 0))
        except OverflowError:
            valid = False
        if not valid:
            requirement = 'positive' if positive else 'nonnegative'
            raise HTTPException(422, f'{name} must be a finite {requirement} number or null.')
        return value

    def text(item, key, default='', limit=100):
        value = item.get(key, default)
        if not isinstance(value, str) or len(value) > limit:
            raise HTTPException(422, f'Taxonomy {key} must be text of up to {limit} characters.')
        return value.strip()

    source = taxonomy.get('source', 'rules')
    if not isinstance(source, str) or source not in {'rules', 'model', 'fallback'}:
        raise HTTPException(422, 'Taxonomy source must be rules, model or fallback.')
    found_reject_section = taxonomy.get('found_reject_section', False)
    if not isinstance(found_reject_section, bool):
        raise HTTPException(422, 'Taxonomy found_reject_section must be a boolean.')
    classes = taxonomy.get('classes')
    if not isinstance(classes, list) or not 1 <= len(classes) <= 12:
        raise HTTPException(422, 'Confirm between one and twelve defect classes.')
    seen = set()
    normalized = []
    for entry in classes:
        if not isinstance(entry, dict):
            raise HTTPException(422, 'Defect classes must be objects.')
        kind = entry.get('defect_type')
        if (not isinstance(kind, str) or len(kind) > 24 or kind == 'good'
                or re.fullmatch(r'[a-z0-9]+(?:_[a-z0-9]+)*', kind) is None or kind in seen):
            raise HTTPException(422, 'Defect class identifiers must be unique valid defect names.')
        label = kind.replace('_', ' ').capitalize()
        normalized.append({'defect_type': kind, 'label': text(entry, 'label', label) or label,
                           'clause': text(entry, 'clause'), 'description': text(entry, 'description', limit=4000),
                           'limit_mm': dimension(entry.get('limit_mm'), 'Defect limit')})
        seen.add(kind)
    return {'part_name': text(taxonomy, 'part_name'),
            'part_width_mm': dimension(taxonomy.get('part_width_mm'), 'Part width', positive=True),
            'classes': normalized, 'source': source, 'found_reject_section': found_reject_section}


@router.patch('/revisions/{id}')
def update_revision(id: str, body: RevisionUpdate, request: Request):
    _, owner, actor = access(request, {'admin'})
    store = records()
    previous = store.get(owner, id, 'revision')
    changes = {'status': body.status}
    if body.taxonomy is not None:
        changes['taxonomy'] = _validate_taxonomy(body.taxonomy)
    if body.status == 'approved' and previous.get('status') == 'draft':
        # Publishing explicitly confirms the displayed parsed taxonomy and instructions.
        if 'taxonomy' not in changes:
            changes['taxonomy'] = _validate_taxonomy(previous.get('taxonomy'))
        changes.update(taxonomy_confirmed=True, approved_by=actor, approved_at=now())
    if body.status == 'retired' and previous.get('status') != 'retired':
        changes.update(retired_by=actor, retired_at=now())
    return store.update(owner, id, body.version, changes, actor)


@router.post('/stations', status_code=201)
def station(body: Station, request: Request):
    _, owner, actor = access(request, EDIT)
    return records().create(owner, 'station', {**body.model_dump(), 'active': True}, actor)


@router.patch('/stations/{id}')
def update_station(id: str, body: StationUpdate, request: Request):
    _, owner, actor = access(request, EDIT)
    store = records()
    store.get(owner, id, 'station')
    changes = body.model_dump(exclude={'version'}, exclude_none=True)
    return store.update(owner, id, body.version, changes, actor)


@router.post('/lots', status_code=201)
def lot(body: Lot, request: Request):
    _, owner, actor = access(request, {'admin', 'engineer', 'operator'})
    return records().create(owner, 'lot', {**body.model_dump(), 'status': 'open'}, actor)


@router.patch('/lots/{id}')
def update_lot(id: str, body: LotUpdate, request: Request):
    _, owner, actor = access(request, EDIT)
    store = records()
    store.get(owner, id, 'lot')
    return store.update(owner, id, body.version, {'status': body.status}, actor)


@router.patch('/reviews/{id}')
def update_review(id: str, body: ReviewUpdate, request: Request):
    _, owner, actor = access(request, EDIT)
    store = records()
    previous = store.get(owner, id, 'review')
    if body.status == 'closed' and (not body.outcome or not body.reason):
        raise HTTPException(422, 'Closing a review requires an outcome and reason.')
    if body.status != 'closed' and body.outcome is not None:
        raise HTTPException(422, 'Set a disposition only when closing the review.')
    if previous.get('quarantined') and body.status == 'closed' and body.outcome == 'accept':
        raise HTTPException(409, 'A quarantined result requires a new valid capture before acceptance.')
    timestamp = now()
    history = [*previous.get('history', []), {'status': body.status, 'outcome': body.outcome,
                                            'reason': body.reason, 'actor': actor, 'at': timestamp}]
    changes = {'status': body.status, 'history': history, 'outcome': body.outcome, 'reason': body.reason}
    if body.status == 'claimed':
        changes.update(assignee=actor, claimed_at=timestamp)
    elif body.status == 'open':
        changes.update(assignee=None, reviewer=None, closed_at=None)
    else:
        changes.update(reviewer=actor, closed_at=timestamp)
    return store.update(owner, id, body.version, changes, actor)


@router.patch('/standards/{id}')
def update_standard(id: str, body: StandardUpdate, request: Request):
    _, owner, actor = access(request, {'admin'})
    store = records()
    previous = store.get(owner, id, 'standard')
    changes = {'status': body.status, 'reason': body.reason}
    if body.status == 'approved':
        revision = store.get(owner, previous['revision_id'], 'revision')
        if revision.get('status') != 'approved':
            raise HTTPException(409, 'Approve the specification revision before its standards.')
        if previous.get('status') == 'candidate':
            changes.update(approver=actor, approved_at=now())
    else:
        changes.update(retired_by=actor, retired_at=now())
    result = store.update(owner, id, body.version, changes, actor)
    if body.status == 'approved' and previous.get('status') == 'candidate':
        # Commit approval first; provider failures remain in the retryable outbox.
        from ..workspace.routes import service
        synced = service.sync_correction(previous['correction_id'])
        result['sync_status'] = synced.get('sync_status', 'pending')
    return result


def _check_assignee(store, owner, user_id):
    if user_id is None:
        return
    with store.engine.connect() as connection:
        exists = connection.execute(sa.select(tables.memberships.c.id).where(
            tables.memberships.c.team_id == owner, tables.memberships.c.user_id == user_id,
            tables.memberships.c.active.is_(True))).first()
    if exists is None:
        raise HTTPException(422, 'Assign an active member of this team.')


@router.post('/nonconformances', status_code=201)
def nonconformance(body: Nonconformance, request: Request):
    _, owner, actor = access(request, EDIT)
    store = records()
    store.get(owner, body.lot_id, 'lot')
    _check_assignee(store, owner, body.assignee)
    if body.inspection_id:
        with store.engine.connect() as connection:
            inspection = connection.execute(sa.select(db.inspections.c.payload).where(
                db.inspections.c.id == body.inspection_id, db.inspections.c.owner_id == owner)).scalar()
        if inspection is None or (inspection.get('pilot') or {}).get('lot_id') != body.lot_id:
            raise HTTPException(404, 'Inspection not found in this lot.')
    return store.create(owner, 'nonconformance', {**body.model_dump(), 'status': 'open', 'created_by': actor,
                                                 'history': []}, actor)


@router.patch('/nonconformances/{id}')
def update_nonconformance(id: str, body: NonconformanceUpdate, request: Request):
    _, owner, actor = access(request, EDIT)
    store = records()
    previous = store.get(owner, id, 'nonconformance')
    changes = body.model_dump(exclude={'version'}, exclude_unset=True)
    _check_assignee(store, owner, changes.get('assignee'))
    updated = {**previous, **changes}
    if body.status == 'contained' and not updated.get('containment'):
        raise HTTPException(422, 'Record containment before marking an issue contained.')
    if body.status == 'closed' and (not updated.get('corrective_action') or not updated.get('resolution')):
        raise HTTPException(422, 'Closure requires corrective action and a resolution.')
    timestamp = now()
    changes['history'] = [*previous.get('history', []), {
        'status': body.status, 'actor': actor, 'at': timestamp,
        'changes': {key: value for key, value in changes.items() if key != 'history'}}]
    if body.status == 'closed':
        changes.update(closed_by=actor, closed_at=timestamp)
    elif previous.get('status') == 'closed':
        changes.update(closed_by=None, closed_at=None)
    return store.update(owner, id, body.version, changes, actor)
