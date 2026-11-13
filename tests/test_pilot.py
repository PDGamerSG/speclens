"""Offline security and lifecycle tests against the real pilot database and HTTP API."""
from concurrent.futures import ThreadPoolExecutor
import json
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

BASE = '/api/workspace/pilot'
PASSWORD = 'correct horse battery staple'


@pytest.fixture
def pilot(tmp_path, monkeypatch):
    from app import db
    from app.pilot.routes import router
    from app.pilot.store import PilotStore
    import app.workspace.routes as workspace
    engine = db.engine(tmp_path / 'pilot.sqlite')
    monkeypatch.setattr(workspace, 'service', SimpleNamespace(store=SimpleNamespace(engine=engine)))
    app = FastAPI()
    app.include_router(router)
    return SimpleNamespace(client=TestClient(app), app=app, engine=engine, store=PilotStore(engine))


def register(client, username='anika', team='Factory A'):
    response = client.post(BASE + '/register', json={
        'username': username, 'password': PASSWORD, 'name': username.title(), 'team_name': team})
    assert response.status_code == 201, response.text
    return response.json()


def invite_member(pilot, role='engineer', username='neha'):
    invitation = pilot.client.post(BASE + '/invites', json={'role': role})
    assert invitation.status_code == 201, invitation.text
    member = TestClient(pilot.app)
    response = member.post(BASE + '/join', json={
        'token': invitation.json()['token'], 'username': username, 'password': PASSWORD, 'name': username.title()})
    assert response.status_code == 201, response.text
    return member, response.json(), invitation.json()


def setup_lot(pilot):
    identity = register(pilot.client)
    product = pilot.client.post(BASE + '/products', json={
        'code': 'P1', 'name': 'Nut', 'factory': 'Factory A'}).json()
    revision = pilot.client.post(BASE + '/revisions', json={
        'product_id': product['id'], 'label': 'A', 'spec_text': 'REJECT\n4.1 Crack: Reject visible cracks.',
        'capture_instructions': 'One top view.'}).json()
    approved = pilot.client.patch(BASE + f'/revisions/{revision["id"]}', json={
        'version': revision['version'], 'status': 'approved'})
    assert approved.status_code == 200, approved.text
    station = pilot.client.post(BASE + '/stations', json={
        'name': 'Bench 1', 'product_id': product['id'], 'instructions': 'Diffuse light.'}).json()
    lot = pilot.client.post(BASE + '/lots', json={
        'reference': 'Lot 1', 'revision_id': revision['id'], 'station_id': station['id']}).json()
    assert lot.get('status') == 'open', lot
    return identity, product, approved.json(), station, lot


def test_registration_stores_scrypt_and_only_hashes_opaque_tokens(pilot):
    from app.pilot import auth, tables
    identity = register(pilot.client)
    assert identity['authenticated'] and identity['role'] == 'admin'
    assert identity['team']['id'].startswith('team-')
    token = pilot.client.cookies.get(auth.COOKIE)
    assert token and len(token) >= 40
    with pilot.engine.connect() as c:
        user = c.execute(sa.select(tables.users)).mappings().one()
        session = c.execute(sa.select(tables.sessions)).mappings().one()
    assert user['password_hash'].startswith('scrypt$') and PASSWORD not in user['password_hash']
    assert token not in str(session) and len(session['token_hash']) == 64


def test_cookie_properties_logout_revocation_and_login(pilot):
    from app.pilot import auth
    response = pilot.client.post(BASE + '/register', json={
        'username': 'anika', 'password': PASSWORD, 'name': 'Anika', 'team_name': 'Factory A'})
    cookie = response.headers['set-cookie'].lower()
    assert 'httponly' in cookie and 'samesite=strict' in cookie and 'path=/' in cookie
    token = pilot.client.cookies.get(auth.COOKIE)
    assert pilot.client.post(BASE + '/logout').status_code == 200
    assert pilot.client.get(BASE + '/session').json()['authenticated'] is False
    pilot.client.cookies.set(auth.COOKIE, token)
    assert pilot.client.get(BASE + '/overview').status_code == 401
    pilot.client.cookies.clear()
    assert pilot.client.post(BASE + '/login', json={'username': 'ANIKA', 'password': PASSWORD}).json()['authenticated']


def test_expired_or_unrecognized_session_never_becomes_anonymous(pilot):
    from app.pilot import auth, tables
    register(pilot.client)
    with pilot.engine.begin() as c:
        c.execute(tables.sessions.update().values(expires_at=0))
    assert pilot.client.get(BASE + '/session').status_code == 401
    pilot.client.cookies.clear()
    pilot.client.cookies.set(auth.COOKIE, 'not-a-session')
    assert pilot.client.get(BASE + '/overview').status_code == 401


def test_current_identity_accepts_explicit_engine(pilot):
    from app.pilot import auth
    from starlette.requests import Request
    identity = register(pilot.client)
    token = pilot.client.cookies.get(auth.COOKIE)
    request = Request({'type': 'http', 'headers': [(b'cookie', f'{auth.COOKIE}={token}'.encode())]})
    assert auth.current_identity(request, engine=pilot.engine)['team'] == identity['team']


def test_invite_is_hashed_one_use_and_role_cannot_be_elevated(pilot):
    from app.pilot import tables
    register(pilot.client)
    member, identity, invite = invite_member(pilot, role='operator')
    assert identity['role'] == 'operator'
    with pilot.engine.connect() as c:
        stored = c.execute(sa.select(tables.invites)).mappings().one()
    assert invite['token'] not in str(stored) and stored['used_at']
    replay = TestClient(pilot.app).post(BASE + '/join', json={
        'token': invite['token'], 'username': 'outsider', 'password': PASSWORD, 'name': 'Other'})
    assert replay.status_code == 422
    assert member.post(BASE + '/products', json={'code': 'X', 'name': 'X', 'factory': 'X'}).status_code == 403
    assert member.post(BASE + '/invites', json={'role': 'admin'}).status_code == 403


def test_expired_invitation_does_not_create_a_user(pilot):
    from app.pilot import tables
    register(pilot.client)
    invite = pilot.client.post(BASE + '/invites', json={'role': 'viewer'}).json()
    with pilot.engine.begin() as c:
        c.execute(tables.invites.update().values(expires_at=0))
    response = TestClient(pilot.app).post(BASE + '/join', json={
        'token': invite['token'], 'username': 'outsider', 'password': PASSWORD, 'name': 'Other'})
    assert response.status_code == 422
    with pilot.engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(tables.users)).scalar_one() == 1


def test_last_admin_cannot_be_demoted_and_disabled_member_loses_session(pilot):
    register(pilot.client)
    member, _, _ = invite_member(pilot)
    members = pilot.client.get(BASE + '/team').json()['members']
    admin = next(m for m in members if m['role'] == 'admin')
    engineer = next(m for m in members if m['role'] == 'engineer')
    assert pilot.client.patch(BASE + f'/members/{admin["id"]}', json={
        'version': admin['version'], 'role': 'viewer', 'active': True}).status_code == 409
    response = pilot.client.patch(BASE + f'/members/{engineer["id"]}', json={
        'version': engineer['version'], 'role': 'engineer', 'active': False})
    assert response.status_code == 200
    assert member.get(BASE + '/overview').status_code == 401
    assert pilot.client.patch(BASE + f'/members/{engineer["id"]}', json={
        'version': engineer['version'], 'role': 'admin', 'active': True}).status_code == 409


def test_team_isolation_and_correct_kind_references(pilot):
    identity, product, revision, station, lot = setup_lot(pilot)
    other = TestClient(pilot.app)
    register(other, username='other', team='Other team')
    assert other.get(BASE + '/overview').json()['products'] == []
    assert other.post(BASE + '/revisions', json={
        'product_id': product['id'], 'label': 'Bad', 'spec_text': 'Reject ink.'}).status_code == 404
    assert pilot.client.post(BASE + '/revisions', json={
        'product_id': station['id'], 'label': 'Wrong kind', 'spec_text': 'Reject ink.'}).status_code == 404
    with pytest.raises(HTTPException) as error:
        pilot.store.get('team-other', lot['id'])
    assert error.value.status_code == 404


def test_auth_rate_limit_works_without_public_demo_mode(pilot):
    register(pilot.client)
    statuses = [pilot.client.post(BASE + '/login', json={
        'username': 'anika', 'password': 'wrong password'}).status_code for _ in range(16)]
    assert 401 in statuses and 429 in statuses


@pytest.mark.parametrize('payload', [
    {'username': 'ab'}, {'username': 'bad name'}, {'password': 'short'}, {'name': '  '}, {'team_name': '  '},
])
def test_registration_rejects_invalid_inputs(pilot, payload):
    response = pilot.client.post(BASE + '/register', json={
        'username': 'anika', 'password': PASSWORD, 'name': 'Anika', 'team_name': 'Factory A', **payload})
    assert response.status_code == 422


def test_versions_and_event_write_are_atomic(pilot):
    identity = register(pilot.client)
    owner = identity['team']['id']
    item = pilot.store.create(owner, 'product', {'code': 'P1', 'name': 'Nut', 'factory': 'A'})
    before = len(pilot.store.list(owner, 'event'))
    changed = pilot.store.update(owner, item['id'], item['version'], {'description': 'Reviewed'})
    assert changed['version'] == 2
    with pytest.raises(HTTPException) as stale:
        pilot.store.update(owner, item['id'], item['version'], {'description': 'Stale'})
    assert stale.value.status_code == 409
    assert len(pilot.store.list(owner, 'event')) == before + 1
    with pytest.raises(HTTPException):
        pilot.store.create(owner, 'product', {'name': 'Duplicate'}, id=item['id'])
    assert len(pilot.store.list(owner, 'event')) == before + 1


def test_concurrent_compare_and_swap_has_one_winner(pilot):
    owner = register(pilot.client)['team']['id']
    item = pilot.store.create(owner, 'product', {'code': 'P1', 'name': 'Nut', 'factory': 'A'})
    def update(value):
        try:
            return pilot.store.update(owner, item['id'], 1, {'description': value})['version']
        except HTTPException as error:
            return error.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(update, ['first', 'second']))
    assert sorted(results) == [2, 409]


def test_approved_revision_and_taxonomy_are_immutable_and_retirement_is_final(pilot):
    identity, _, revision, _, _ = setup_lot(pilot)
    owner = identity['team']['id']
    assert revision['status'] == 'approved' and revision['taxonomy']['classes'][0]['defect_type'] == 'crack'
    for change in ({'spec_text': 'Accept everything'}, {'taxonomy': {'classes': []}}):
        with pytest.raises(HTTPException) as immutable:
            pilot.store.update(owner, revision['id'], revision['version'], change)
        assert immutable.value.status_code == 409
    retired = pilot.client.patch(BASE + f'/revisions/{revision["id"]}', json={
        'version': revision['version'], 'status': 'retired'}).json()
    assert pilot.client.patch(BASE + f'/revisions/{revision["id"]}', json={
        'version': retired['version'], 'status': 'approved'}).status_code == 409


def draft_revision(pilot):
    identity = register(pilot.client)
    product = pilot.client.post(BASE + '/products', json={
        'code': 'P1', 'name': 'Nut', 'factory': 'Factory A'}).json()
    revision = pilot.client.post(BASE + '/revisions', json={
        'product_id': product['id'], 'label': 'A', 'spec_text': 'REJECT\n4.1 Crack: Reject visible cracks.'}).json()
    return identity['team']['id'], revision


def test_approval_normalizes_optional_taxonomy_fields_for_mask_measurement(pilot, tmp_path):
    import numpy as np
    from PIL import Image
    from app.workspace.memory import HindsightMemory
    from app.workspace.service import WorkspaceService

    owner, revision = draft_revision(pilot)
    response = pilot.client.patch(BASE + f'/revisions/{revision["id"]}', json={
        'version': 1, 'status': 'approved', 'taxonomy': {'classes': [{'defect_type': 'crack'}]}})
    assert response.status_code == 200, response.text
    taxonomy = response.json()['taxonomy']
    assert taxonomy['part_width_mm'] is None and taxonomy['part_name'] == ''
    assert taxonomy['source'] == 'rules' and taxonomy['found_reject_section'] is False
    assert taxonomy['classes'] == [{'defect_type': 'crack', 'label': 'Crack', 'clause': '',
                                    'description': '', 'limit_mm': None}]
    assert pilot.store.get(owner, revision['id'])['taxonomy'] == taxonomy
    # Exercise the exact consumer that previously raised after a provider returned a mask.
    service = WorkspaceService(SimpleNamespace(engine=pilot.engine), HindsightMemory(''), media_root=tmp_path / 'media')
    mask = np.zeros((32, 32), dtype=bool)
    mask[8:16, 8:16] = True
    result = service.save_mask('insp-taxonomy', Image.new('RGB', (32, 32)), mask,
        {'verdict': 'defect', 'type': 'crack', 'part_box_px': [0, 0, 32, 32]}, taxonomy)
    assert result['measurement']['limit_mm'] is None
    assert result['measurement']['mm_per_px'] is None


@pytest.mark.parametrize('source', ['rules', 'model', 'fallback'])
def test_approval_preserves_finite_dimensions_and_known_taxonomy_sources(pilot, source):
    _, revision = draft_revision(pilot)
    response = pilot.client.patch(BASE + f'/revisions/{revision["id"]}', json={
        'version': 1, 'status': 'approved', 'taxonomy': {'part_name': 'Nut', 'part_width_mm': 20.5,
            'source': source, 'found_reject_section': True, 'classes': [{'defect_type': 'crack', 'label': 'Shell crack',
                'clause': '4.1', 'description': 'Reject cracks.', 'limit_mm': 0}]}})
    assert response.status_code == 200, response.text
    taxonomy = response.json()['taxonomy']
    assert taxonomy['part_width_mm'] == 20.5 and taxonomy['classes'][0]['limit_mm'] == 0
    assert taxonomy['source'] == source and taxonomy['found_reject_section'] is True


@pytest.mark.parametrize('field,value', [
    *[('part_width_mm', value) for value in ['20', 'wide', 0, -1, True, {}, [], float('nan'), float('inf'), -float('inf')]],
    *[('limit_mm', value) for value in ['2', 'wide', -1, True, {}, [], float('nan'), float('inf'), -float('inf')]],
    ('part_name', {}), ('part_name', 'n' * 101), ('source', 'custom'), ('source', None),
    ('found_reject_section', 'true'), ('label', []), ('label', 'l' * 101),
    ('clause', {}), ('clause', 'c' * 101), ('description', 12), ('description', 'd' * 4001),
    ('defect_type', ''), ('defect_type', 'good'), ('defect_type', 'Bad name'), ('defect_type', 'a' * 25),
])
def test_approval_rejects_malformed_taxonomy_without_mutating_draft(pilot, field, value):
    owner, revision = draft_revision(pilot)
    taxonomy = {'classes': [{'defect_type': 'crack'}]}
    if field in {'limit_mm', 'label', 'clause', 'description', 'defect_type'}:
        taxonomy['classes'][0][field] = value
    else:
        taxonomy[field] = value
    response = pilot.client.patch(BASE + f'/revisions/{revision["id"]}',
        content=json.dumps({'version': 1, 'status': 'approved', 'taxonomy': taxonomy}),
        headers={'content-type': 'application/json'})
    assert response.status_code == 422, response.text
    saved = pilot.store.get(owner, revision['id'])
    assert saved['version'] == 1 and saved['status'] == 'draft' and saved['taxonomy'] == revision['taxonomy']


@pytest.mark.parametrize('classes', [[], [{}], [{'defect_type': 'crack'}, {'defect_type': 'crack'}], 'crack', None])
def test_approval_requires_nonempty_unique_taxonomy_classes(pilot, classes):
    _, revision = draft_revision(pilot)
    response = pilot.client.patch(BASE + f'/revisions/{revision["id"]}', json={
        'version': 1, 'status': 'approved', 'taxonomy': {'classes': classes}})
    assert response.status_code == 422


def test_approval_also_validates_stored_draft_taxonomy_when_omitted_from_patch(pilot):
    owner, revision = draft_revision(pilot)
    malformed = pilot.store.update(owner, revision['id'], 1, {'taxonomy': {
        'part_width_mm': 'twenty', 'classes': [{'defect_type': 'crack'}]}})
    response = pilot.client.patch(BASE + f'/revisions/{revision["id"]}', json={
        'version': malformed['version'], 'status': 'approved'})
    assert response.status_code == 422
    assert pilot.store.get(owner, revision['id'])['status'] == 'draft'


def test_capture_context_requires_open_approved_compatible_records(pilot):
    from app.pilot.auth import actor_for
    identity, product, revision, station, lot = setup_lot(pilot)
    owner = identity['team']['id']
    args = dict(revision_id=revision['id'], lot_id=lot['id'], station_id=station['id'],
                physical_part_id='part-1', capture_id='capture-1')
    context = pilot.store.capture_context(owner, actor_for(identity), **args)
    assert context['spec_text'] == revision['spec_text'] and context['taxonomy'] == revision['taxonomy']
    assert context['revision_version'] == revision['version'] and context['actor']['id'] == identity['user']['id']
    assert 'Diffuse light' in context['instructions'] and 'top view' in context['instructions']
    pilot.client.patch(BASE + f'/stations/{station["id"]}', json={'version': 1, 'active': False})
    with pytest.raises(HTTPException) as inactive:
        pilot.store.capture_context(owner, actor_for(identity), **args)
    assert inactive.value.status_code == 409


def test_lot_closure_blocks_pending_captures_and_unresolved_disposition(pilot):
    identity, _, revision, station, lot = setup_lot(pilot)
    owner = identity['team']['id']
    review = pilot.store.create(owner, 'review', {'lot_id': lot['id'], 'revision_id': revision['id'],
        'status': 'open', 'inspection_id': 'inspection-1', 'physical_part_id': 'part-1'})
    def close_lot():
        return pilot.client.patch(BASE + f'/lots/{lot["id"]}', json={'version': lot['version'], 'status': 'closed'})
    assert close_lot().status_code == 409
    hold = pilot.client.patch(BASE + f'/reviews/{review["id"]}', json={
        'version': 1, 'status': 'closed', 'outcome': 'hold', 'reason': 'Need another view.'})
    assert hold.status_code == 200 and close_lot().status_code == 409
    reopened = pilot.client.patch(BASE + f'/reviews/{review["id"]}', json={'version': 2, 'status': 'open'}).json()
    accepted = pilot.client.patch(BASE + f'/reviews/{review["id"]}', json={
        'version': reopened['version'], 'status': 'closed', 'outcome': 'accept', 'reason': 'Verified against clause.'})
    assert accepted.status_code == 200
    assert close_lot().status_code == 200
    assert pilot.store.list(owner, 'standard') == []
    assert len(pilot.store.get(owner, review['id'])['history']) == 3


def test_pending_capture_blocks_lot_closure(pilot):
    identity, _, revision, station, lot = setup_lot(pilot)
    pilot.store.create(identity['team']['id'], 'capture', {'lot_id': lot['id'], 'revision_id': revision['id'],
        'station_id': station['id'], 'physical_part_id': 'part-1', 'status': 'pending'})
    assert pilot.client.patch(BASE + f'/lots/{lot["id"]}', json={'version': 1, 'status': 'closed'}).status_code == 409


def test_explicit_valid_retake_resolves_quarantined_attempt_without_erasing_it(pilot):
    from app import db
    identity, _, revision, station, lot = setup_lot(pilot)
    owner = identity['team']['id']
    fields = {'lot_id': lot['id'], 'revision_id': revision['id'], 'station_id': station['id'],
              'physical_part_id': 'part-1'}
    original = pilot.store.create(owner, 'capture', {**fields, 'status': 'quarantined'}, id='capture-old')
    replacement = pilot.store.create(owner, 'capture', {
        **fields, 'status': 'done', 'retake_of': original['id'], 'inspection_id': 'insp-replacement'}, id='capture-new')
    original = pilot.store.update(owner, original['id'], 1, {'resolved_by': replacement['id']})
    review = pilot.store.create(owner, 'review', {**fields, 'status': 'closed', 'outcome': 'retake',
        'capture_id': original['id'], 'quarantined': True, 'resolved_by': replacement['id']})
    new_review = pilot.store.create(owner, 'review', {**fields, 'status': 'open', 'capture_id': replacement['id']})
    close = lambda: pilot.client.patch(BASE + f'/lots/{lot["id"]}', json={'version': 1, 'status': 'closed'})
    assert close().status_code == 409
    pilot.client.patch(BASE + f'/reviews/{new_review["id"]}', json={
        'version': 1, 'status': 'closed', 'outcome': 'accept', 'reason': 'Valid repeat capture.'})
    # A link alone is insufficient: its inspection must really exist in this team and capture.
    assert close().status_code == 409
    with pilot.engine.begin() as connection:
        connection.execute(db.inspections.insert().values(id='insp-replacement', scope_id='scope-1',
            owner_id=owner, created_at='2026-11-14T00:00:00+00:00', payload={
                'pilot': {**fields, 'capture_id': replacement['id'], 'quarantined': False}}))
    assert close().status_code == 200
    assert pilot.store.get(owner, original['id'])['status'] == 'quarantined'
    assert pilot.store.get(owner, review['id'])['outcome'] == 'retake'


def test_new_raw_capture_cannot_enter_a_closed_lot(pilot):
    identity, _, revision, station, lot = setup_lot(pilot)
    closed = pilot.client.patch(BASE + f'/lots/{lot["id"]}', json={'version': 1, 'status': 'closed'})
    assert closed.status_code == 200
    with pytest.raises(HTTPException) as error:
        pilot.store.create(identity['team']['id'], 'capture', {'lot_id': lot['id'], 'revision_id': revision['id'],
            'station_id': station['id'], 'physical_part_id': 'part-1', 'status': 'pending'})
    assert error.value.status_code == 409


def test_review_claim_and_disposition_are_attributable_and_not_teaching(pilot):
    identity, _, revision, _, lot = setup_lot(pilot)
    member, member_identity, _ = invite_member(pilot)
    owner = identity['team']['id']
    review = pilot.store.create(owner, 'review', {'lot_id': lot['id'], 'revision_id': revision['id'], 'status': 'open'})
    claimed = member.patch(BASE + f'/reviews/{review["id"]}', json={'version': 1, 'status': 'claimed'}).json()
    assert claimed['assignee']['id'] == member_identity['user']['id']
    assert member.patch(BASE + f'/reviews/{review["id"]}', json={
        'version': 2, 'status': 'closed', 'outcome': 'reject'}).status_code == 422
    closed = member.patch(BASE + f'/reviews/{review["id"]}', json={
        'version': 2, 'status': 'closed', 'outcome': 'reject', 'reason': 'Crack confirmed.'}).json()
    assert closed['reviewer']['id'] == member_identity['user']['id']
    assert pilot.store.list(owner, 'standard') == []


def test_nonconformance_requires_containment_and_closure_evidence(pilot):
    identity, _, _, _, lot = setup_lot(pilot)
    response = pilot.client.post(BASE + '/nonconformances', json={
        'title': 'Cracks', 'lot_id': lot['id'], 'severity': 'major', 'description': 'Three cracked parts.',
        'assignee': identity['user']['id']})
    assert response.status_code == 201, response.text
    issue = response.json()
    path = BASE + f'/nonconformances/{issue["id"]}'
    assert pilot.client.patch(path, json={'version': 1, 'status': 'contained'}).status_code == 422
    assert pilot.client.patch(path, json={'version': 1, 'status': 'closed', 'resolution': 'Done'}).status_code == 422
    contained = pilot.client.patch(path, json={'version': 1, 'status': 'contained', 'containment': 'Isolated lot.'}).json()
    closed = pilot.client.patch(path, json={'version': contained['version'], 'status': 'closed',
        'corrective_action': 'Replace damaged fixture.', 'resolution': 'Reinspected retained stock.'})
    assert closed.status_code == 200 and len(closed.json()['history']) == 2
    assert closed.json()['closed_by']['id'] == identity['user']['id']


def test_nonconformance_preserves_requirement_cause_and_effectiveness_evidence(pilot):
    _, _, _, _, lot = setup_lot(pilot)
    response = pilot.client.post(BASE + '/nonconformances', json={
        'title': 'Fixture damage', 'lot_id': lot['id'], 'severity': 'major',
        'description': 'Cracks at fixture edge.', 'requirement': 'Clause 4.1: no visible cracks.',
        'root_cause': 'Fixture edge worn.', 'evidence': 'Retained sample photographs.'})
    assert response.status_code == 201, response.text
    issue = response.json()
    assert issue['requirement'].startswith('Clause 4.1')
    updated = pilot.client.patch(BASE + f'/nonconformances/{issue["id"]}', json={
        'version': issue['version'], 'status': 'closed', 'corrective_action': 'Replace fixture.',
        'resolution': 'Inspected retained parts.', 'evidence': 'Two subsequent lots checked with no recurrence.'})
    assert updated.status_code == 200 and updated.json()['root_cause'] == 'Fixture edge worn.'
    assert 'subsequent lots' in updated.json()['evidence']
    assert updated.json()['history'][-1]['changes']['evidence'] == updated.json()['evidence']


def test_only_admin_publishes_standards_and_sync_starts_after_commit(pilot, monkeypatch):
    from app.pilot.auth import actor_for
    import app.workspace.routes as workspace
    identity, _, revision, _, lot = setup_lot(pilot)
    owner = identity['team']['id']
    candidate = pilot.store.create(owner, 'standard', {'revision_id': revision['id'], 'lot_id': lot['id'],
        'correction_id': 'correction-1', 'inspection_id': 'inspection-1', 'clause': '4.1',
        'rule_text': 'Reject visible cracks.', 'verdict': 'defect', 'defect_type': 'crack'}, actor_for(identity))
    member, _, _ = invite_member(pilot)
    path = BASE + f'/standards/{candidate["id"]}'
    assert member.patch(path, json={'version': 1, 'status': 'approved'}).status_code == 403
    synced = []
    def sync(correction_id):
        approved = pilot.store.get(owner, candidate['id'])
        assert approved['status'] == 'approved'
        synced.append(correction_id)
        return {'sync_status': 'pending'}
    monkeypatch.setattr(workspace.service, 'sync_correction', sync, raising=False)
    response = pilot.client.patch(path, json={'version': 1, 'status': 'approved'})
    assert response.status_code == 200, response.text
    approved = response.json()
    assert synced == ['correction-1'] and approved['sync_status'] == 'pending'
    assert approved['approver']['id'] == identity['user']['id']
    with pytest.raises(HTTPException) as error:
        pilot.store.update(owner, approved['id'], approved['version'], {'rule_text': 'Accept cracks.'})
    assert error.value.status_code == 409
    retired = pilot.client.patch(path, json={'version': approved['version'], 'status': 'retired', 'reason': 'Replaced.'})
    assert retired.status_code == 200 and synced == ['correction-1']
    assert pilot.client.patch(path, json={'version': retired.json()['version'], 'status': 'approved'}).status_code == 409


def test_all_reference_fields_reject_cross_team_and_wrong_kind(pilot):
    identity, product, revision, station, lot = setup_lot(pilot)
    owner = identity['team']['id']
    for kind, fields in [('station', {'product_id': revision['id']}),
                         ('lot', {'revision_id': product['id'], 'station_id': station['id']}),
                         ('review', {'lot_id': station['id']}),
                         ('standard', {'revision_id': lot['id']}),
                         ('capture', {'lot_id': product['id']})]:
        with pytest.raises(HTTPException) as invalid:
            pilot.store.create(owner, kind, fields)
        assert invalid.value.status_code == 404


def test_capture_context_rejects_wrong_lot_product_and_retake_part(pilot):
    from app.pilot.auth import actor_for
    identity, _, revision, station, lot = setup_lot(pilot)
    owner = identity['team']['id']
    actor = actor_for(identity)
    another_product = pilot.store.create(owner, 'product', {'code': 'P2', 'name': 'Other', 'factory': 'A'})
    another_station = pilot.store.create(owner, 'station', {'name': 'Wrong bench',
        'product_id': another_product['id'], 'instructions': 'Light'})
    args = dict(revision_id=revision['id'], lot_id=lot['id'], station_id=station['id'],
                physical_part_id='part-1', capture_id='capture-2')
    with pytest.raises(HTTPException) as incompatible:
        pilot.store.capture_context(owner, actor, **{**args, 'station_id': another_station['id']})
    assert incompatible.value.status_code == 422
    pilot.store.create(owner, 'capture', {**args, 'status': 'done'}, id='capture-1')
    with pytest.raises(HTTPException) as wrong_part:
        pilot.store.capture_context(owner, actor, **{**args, 'physical_part_id': 'part-2', 'retake_of': 'capture-1'})
    assert wrong_part.value.status_code == 422
    assert pilot.store.capture_context(owner, actor, **args, retake_of='capture-1')['retake_of'] == 'capture-1'


def test_viewer_can_read_but_cannot_mutate_domain_records(pilot):
    _, _, revision, station, lot = setup_lot(pilot)
    viewer, _, _ = invite_member(pilot, 'viewer')
    assert viewer.get(BASE + '/overview').status_code == 200
    assert viewer.get(BASE + '/team').status_code == 403
    assert viewer.post(BASE + '/lots', json={
        'reference': 'Lot 2', 'revision_id': revision['id'], 'station_id': station['id']}).status_code == 403
    assert viewer.patch(BASE + f'/lots/{lot["id"]}', json={'version': 1, 'status': 'closed'}).status_code == 403


def test_concurrent_admin_demotion_preserves_one_active_admin(pilot):
    register(pilot.client)
    other, _, _ = invite_member(pilot, 'admin')
    admins = pilot.client.get(BASE + '/team').json()['members']
    def demote(pair):
        client, member = pair
        return client.patch(BASE + f'/members/{member["id"]}', json={
            'version': member['version'], 'role': 'engineer', 'active': True}).status_code
    # Each admin demotes itself. Team lock must preserve the invariant across requests.
    own = next(m for m in admins if m['username'] == 'anika')
    theirs = next(m for m in admins if m['username'] == 'neha')
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(demote, [(pilot.client, own), (other, theirs)]))
    assert sorted(statuses) == [200, 409]


def test_password_and_tokens_do_not_leak_into_overview_or_team(pilot):
    identity = register(pilot.client)
    _, _, invitation = invite_member(pilot)
    overview = pilot.client.get(BASE + '/overview').text
    team = pilot.client.get(BASE + '/team').text
    for secret in (PASSWORD, invitation['token'], pilot.client.cookies.get('speclens_session')):
        assert secret not in overview and secret not in team
    assert identity['user']['username'] in overview


def test_cross_origin_cookie_writes_are_rejected(pilot):
    register(pilot.client)
    response = pilot.client.post(BASE + '/products', headers={'origin': 'https://evil.example'},
                                 json={'code': 'P1', 'name': 'Nut', 'factory': 'A'})
    assert response.status_code == 403


def test_https_sessions_are_secure_and_downgraded_origin_is_rejected(pilot):
    client = TestClient(pilot.app, base_url='https://factory.example')
    response = client.post(BASE + '/register', json={
        'username': 'secure.user', 'password': PASSWORD, 'name': 'Secure', 'team_name': 'Factory'})
    assert response.status_code == 201 and 'secure' in response.headers['set-cookie'].lower()
    assert client.post(BASE + '/products', headers={'origin': 'http://factory.example'},
        json={'code': 'P1', 'name': 'Nut', 'factory': 'A'}).status_code == 403
    assert 'no-store' in client.get(BASE + '/session').headers.get('cache-control', '')


def test_only_exact_configured_https_origins_can_write_through_backend_proxy(pilot, monkeypatch):
    monkeypatch.setenv('SPECLENS_ALLOWED_ORIGINS', ' https://factory.example/ , https://factory.vercel.app ')
    client = TestClient(pilot.app, base_url='https://backend.example')
    response = client.post(BASE + '/register', headers={'origin': 'https://factory.example'}, json={
        'username': 'proxy.user', 'password': PASSWORD, 'name': 'Proxy', 'team_name': 'Factory'})
    assert response.status_code == 201, response.text
    for origin in ['https://factory.vercel.app', 'https://backend.example']:
        assert client.post(BASE + '/products', headers={'origin': origin},
            json={'code': 'P1', 'name': 'Nut', 'factory': 'A'}).status_code == 201
    for origin in ['http://factory.example', 'https://factory.example.evil.test',
                   'https://evil-factory.example', 'https://factory.example/path']:
        assert client.post(BASE + '/products', headers={'origin': origin},
            json={'code': 'P1', 'name': 'Nut', 'factory': 'A'}).status_code == 403


def test_audit_failure_rolls_back_record_mutation(pilot, monkeypatch):
    owner = register(pilot.client)['team']['id']
    item = pilot.store.create(owner, 'product', {'code': 'P1', 'name': 'Nut', 'factory': 'A'})
    def fail(*args, **kwargs):
        raise RuntimeError('Audit store unavailable')
    monkeypatch.setattr(pilot.store, '_event', fail)
    with pytest.raises(RuntimeError, match='Audit store unavailable'):
        pilot.store.update(owner, item['id'], 1, {'description': 'Should roll back'})
    assert pilot.store.get(owner, item['id']) == item


def test_role_changes_apply_to_existing_sessions_and_reactivation_does_not_revive_them(pilot):
    register(pilot.client)
    member, _, _ = invite_member(pilot)
    membership = next(m for m in pilot.client.get(BASE + '/team').json()['members'] if m['role'] == 'engineer')
    path = BASE + f'/members/{membership["id"]}'
    changed = pilot.client.patch(path, json={'version': 1, 'role': 'viewer', 'active': True})
    assert changed.status_code == 200
    assert member.get(BASE + '/session').json()['role'] == 'viewer'
    assert member.post(BASE + '/products', json={'code': 'X', 'name': 'X', 'factory': 'X'}).status_code == 403
    assert pilot.client.patch(path, json={'version': 2, 'role': 'viewer', 'active': False}).status_code == 200
    assert pilot.client.patch(path, json={'version': 3, 'role': 'engineer', 'active': True}).status_code == 200
    assert member.get(BASE + '/session').status_code == 401


def test_concurrent_invitation_redemption_has_one_winner(pilot):
    register(pilot.client)
    invite = pilot.client.post(BASE + '/invites', json={'role': 'engineer'}).json()
    def redeem(username):
        return TestClient(pilot.app).post(BASE + '/join', json={
            'token': invite['token'], 'username': username, 'password': PASSWORD, 'name': username}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(redeem, ['member.one', 'member.two']))
    assert sorted(statuses) == [201, 422]


def test_failed_duplicate_username_redemption_preserves_the_invitation(pilot):
    register(pilot.client)
    invite = pilot.client.post(BASE + '/invites', json={'role': 'viewer'}).json()
    response = TestClient(pilot.app).post(BASE + '/join', json={
        'token': invite['token'], 'username': 'anika', 'password': PASSWORD, 'name': 'Other'})
    assert response.status_code == 409
    response = TestClient(pilot.app).post(BASE + '/join', json={
        'token': invite['token'], 'username': 'other.member', 'password': PASSWORD, 'name': 'Other'})
    assert response.status_code == 201


def test_metadata_and_actor_spoofing_are_rejected(pilot):
    identity, _, revision, _, lot = setup_lot(pilot)
    response = pilot.client.post(BASE + '/products', json={
        'code': 'P1', 'name': 'Nut', 'factory': 'A', 'owner_id': 'team-victim'})
    assert response.status_code == 422
    review = pilot.store.create(identity['team']['id'], 'review', {'lot_id': lot['id'], 'revision_id': revision['id']})
    assert pilot.client.patch(BASE + f'/reviews/{review["id"]}', json={
        'version': 1, 'status': 'claimed', 'assignee': {'id': 'victim'}}).status_code == 422
    with pytest.raises(HTTPException) as error:
        pilot.store.update(identity['team']['id'], review['id'], 1, {'owner_id': 'team-victim'})
    assert error.value.status_code == 422


def test_immutable_events_and_validation_manifests(pilot):
    owner = register(pilot.client)['team']['id']
    event = pilot.store.list(owner, 'event')[0]
    run = pilot.store.create(owner, 'validation', {'name': 'Study', 'manifest': {'cases': []}})
    for item in (event, run):
        with pytest.raises(HTTPException) as error:
            pilot.store.update(owner, item['id'], item['version'], {'name': 'Altered'})
        assert error.value.status_code == 409


def test_factory_insights_need_a_session_and_stay_inside_the_team(pilot):
    assert pilot.client.get(BASE + '/insights').status_code == 401
    setup_lot(pilot)
    view = pilot.client.get(BASE + '/insights', params={'days': 7})
    assert view.status_code == 200, view.text
    body = view.json()
    assert body['kpis']['open_lots'] == 1 and body['kpis']['products'] == 1
    assert len(body['daily']) == 8
    assert [row['code'] for row in body['products']] == ['P1']
    assert body['attention'] == [], 'an empty open lot is not ready to close'
    other = TestClient(pilot.app)
    register(other, username='ravi', team='Factory B')
    assert other.get(BASE + '/insights').json()['kpis']['products'] == 0
    assert pilot.client.get(BASE + '/insights', params={'days': 0}).status_code == 422
