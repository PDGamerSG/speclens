"""The factory workflow must preserve the public inspector's evidence and governance boundaries."""
import io

import httpx
import pytest
from PIL import Image

from app.workspace.memory import HindsightMemory
from app.workspace.service import WorkspaceService
from app.workspace.store import Scope, Store


def png(color='brown'):
    out = io.BytesIO()
    Image.new('RGB', (80, 80), color).save(out, 'PNG')
    return out.getvalue()


def test_catalog_scope_uses_stable_revision_identity():
    a = Scope('Factory A', 'Part A', 'Reject cracks.', 'team-a', revision_id='revision-a')
    renamed = Scope('New factory label', 'New part label', 'Reject cracks.', 'team-a', revision_id='revision-a')
    assert a.id == renamed.id
    assert a.id != Scope('Factory A', 'Part A', 'Reject cracks.', 'team-b', revision_id='revision-a').id
    assert a.id != Scope('Factory A', 'Part A', 'Reject cracks.', 'team-a', revision_id='revision-b').id


def test_saved_taxonomy_is_owned_even_when_spec_text_matches(tmp_path):
    service = WorkspaceService(Store(tmp_path / 'db.sqlite'), HindsightMemory(''), media_root=tmp_path / 'media')
    text = 'Reject ink.'
    first = {'source': 'model', 'part_name': 'A', 'part_width_mm': 10, 'classes': []}
    second = {'source': 'model', 'part_name': 'B', 'part_width_mm': 20, 'classes': []}
    service.save_taxonomy(text, first, owner_id='visitor-a')
    service.save_taxonomy(text, second, owner_id='visitor-b')
    assert service.taxonomy(text, owner_id='visitor-a')['part_width_mm'] == 10
    assert service.taxonomy(text, owner_id='visitor-b')['part_width_mm'] == 20
    assert service.taxonomy(text)['source'] != 'model'


def lane(tmp_path):
    from app.pilot.store import PilotStore
    store = Store(tmp_path / 'pilot.sqlite')
    pilot = PilotStore(store.engine)
    actor = {'id': 'user-quality', 'name': 'Quality owner', 'username': 'quality', 'role': 'admin'}
    team = 'team-factory'
    product = pilot.create(team, 'product', {'code': 'P-01', 'name': 'Shell', 'factory': 'Factory A'}, actor=actor)
    taxonomy = {'part_name': 'Shell', 'part_width_mm': None, 'source': 'rules', 'classes': [
        {'defect_type': 'print', 'label': 'Print', 'clause': '1', 'description': 'Reject ink.', 'limit_mm': None}]}
    revision = pilot.create(team, 'revision', {'product_id': product['id'], 'label': 'A', 'spec_text': 'Reject ink.',
        'taxonomy': taxonomy, 'capture_instructions': 'One part, top down.', 'status': 'approved'}, actor=actor)
    station = pilot.create(team, 'station', {'name': 'Bench 1', 'product_id': product['id'],
        'instructions': 'Fixed light.', 'active': True}, actor=actor)
    lot = pilot.create(team, 'lot', {'reference': 'LOT-1', 'revision_id': revision['id'], 'station_id': station['id'],
        'status': 'open'}, actor=actor)
    def context(capture='capture-one', part='part-one'):
        return pilot.capture_context(team, actor, revision_id=revision['id'], lot_id=lot['id'], station_id=station['id'],
            physical_part_id=part, capture_id=capture)
    observed = {'calls': 0, 'retains': 0, 'sources': [], 'after': None}
    def memory_response(request):
        if request.url.path.endswith('/memories'):
            observed['retains'] += 1
            return httpx.Response(200, json={'success': True, 'items_count': 1})
        corrections = store.corrections(Scope('Factory A', 'Shell', 'Reject ink.', team, revision_id=revision['id']).id)
        return httpx.Response(200, json={'results': [
            {'id': 'fact-'+c['id'], 'text': c['rule_text'], 'document_id': c['id'], 'type': 'world'} for c in corrections]})
    def inspector(image, spec, classes, **options):
        observed['calls'] += 1
        observed['sources'] = options.get('memory_context', [])
        if observed['after']:
            observed['after']()
        return {'verdict': 'good', 'defect': False, 'type': 'good', 'confidence': .8,
            'rationale': 'No visible ink.', 'box_px': None, 'mask': None, 'ms': 2, 'cost_usd': .001}
    service = WorkspaceService(store, HindsightMemory('https://memory.example', 'key',
        transport=httpx.MockTransport(memory_response)), inspector=inspector, media_root=tmp_path / 'media')
    scope = Scope('Factory A', 'Shell', 'Reject ink.', team, revision_id=revision['id'])
    return service, pilot, actor, scope, context, observed


def test_pilot_capture_retries_save_one_assessment_and_open_one_review(tmp_path):
    service, pilot, actor, scope, context, observed = lane(tmp_path)
    capture = context()
    first = service.run(png(), 'part.png', scope, use_memory=False, context=capture)
    restored = WorkspaceService(service.store, service.memory, inspector=service.inspector, media_root=tmp_path / 'media')
    again = restored.run(png(), 'part.png', scope, use_memory=False, context=capture)
    assert again['id'] == first['id']
    assert observed['calls'] == 1
    reviews = pilot.list(scope.owner_id, 'review')
    assert len(reviews) == 1
    assert reviews[0]['inspection_id'] == first['id']
    assert reviews[0]['status'] == 'open'
    assert first['pilot']['lot_id'] == capture['lot_id']
    assert first['pilot']['actor']['id'] == actor['id']
    with pytest.raises(Exception, match='different|reused|match'):
        restored.run(png('red'), 'changed.png', scope, use_memory=False, context=capture)


def test_pilot_correction_requires_approval_and_retired_rule_cannot_reenter_prompt(tmp_path):
    service, pilot, actor, scope, context, observed = lane(tmp_path)
    first = service.run(png(), 'part.png', scope, use_memory=False, context=context())
    correction = service.correct(first['id'], verdict='defect', defect_type='print',
        rule_text='White letters are ink and must be rejected.', reviewer=actor['name'])
    assert observed['retains'] == 0
    service.drain_outbox()
    assert observed['retains'] == 0
    standard = pilot.list(scope.owner_id, 'standard')[0]
    assert standard['status'] == 'candidate'
    approved = pilot.update(scope.owner_id, standard['id'], standard['version'], {'status': 'approved'}, actor=actor)
    service.sync_correction(correction['id'])
    assert observed['retains'] == 1
    second = service.run(png(), 'second.png', scope, use_memory=True, context=context('capture-two', 'part-two'))
    assert [s['source_id'] for s in second['memories']] == [correction['id']]
    pilot.update(scope.owner_id, approved['id'], approved['version'], {'status': 'retired'}, actor=actor)
    third = service.run(png(), 'third.png', scope, use_memory=True, context=context('capture-three', 'part-three'))
    assert third['memories'] == []
    assert observed['sources'] == []


def test_withdrawal_during_a_model_call_preserves_but_quarantines_evidence(tmp_path):
    service, pilot, actor, scope, context, observed = lane(tmp_path)
    first = service.run(png(), 'part.png', scope, use_memory=False, context=context())
    correction = service.correct(first['id'], verdict='defect', defect_type='print',
        rule_text='White letters are ink and must be rejected.', reviewer=actor['name'])
    standard = pilot.list(scope.owner_id, 'standard')[0]
    approved = pilot.update(scope.owner_id, standard['id'], standard['version'], {'status': 'approved'}, actor=actor)
    service.sync_correction(correction['id'])
    observed['after'] = lambda: pilot.update(scope.owner_id, approved['id'], approved['version'], {'status': 'retired'}, actor=actor)
    result = service.run(png(), 'later.png', scope, use_memory=True, context=context('capture-later', 'part-later'))
    assert result['memories'][0]['source_id'] == correction['id']
    assert result['pilot']['quarantined'] is True
    review = next(r for r in pilot.list(scope.owner_id, 'review') if r['inspection_id'] == result['id'])
    assert review['quarantined'] is True
    assert review['status'] == 'open'


def test_quarantined_capture_cannot_become_a_teaching_standard(tmp_path):
    from app.jobs.queue import JobFailed
    service, pilot, actor, scope, context, observed = lane(tmp_path)
    station = pilot.list(scope.owner_id, 'station')[0]
    observed['after'] = lambda: pilot.update(scope.owner_id, station['id'], station['version'],
        {'active': False}, actor=actor)
    result = service.run(png(), 'part.png', scope, use_memory=False, context=context())
    assert result['pilot']['quarantined']
    with pytest.raises(JobFailed) as quarantine:
        service.correct(result['id'], verdict='defect', defect_type='print',
            rule_text='Reject visible ink markings.', reviewer=actor['name'])
    assert quarantine.value.status_code == 409
    assert service.store.corrections(scope.id) == []
    assert pilot.list(scope.owner_id, 'standard') == []


def test_demo_retention_does_not_expire_factory_evidence(tmp_path):
    service, pilot, actor, scope, context, _ = lane(tmp_path)
    result = service.run(png(), 'part.png', scope, use_memory=False, context=context())
    service.store.purge_before('2099-01-01T00:00:00+00:00', 0)
    assert service.store.inspection(result['id']) is not None
    assert pilot.list(scope.owner_id, 'review')


def test_valid_retake_resolves_prior_attempt_but_preserves_its_review(tmp_path):
    service, pilot, actor, scope, context, _ = lane(tmp_path)
    first = service.run(png(), 'part.png', scope, use_memory=False, context=context())
    review = pilot.list(scope.owner_id, 'review')[0]
    pilot.update(scope.owner_id, review['id'], review['version'],
        {'status': 'closed', 'outcome': 'retake', 'reason': 'Need a clearer view.'}, actor=actor)
    retake_context = {**context('capture-retake', 'part-one'), 'retake_of': first['pilot']['capture_id']}
    second = service.run(png(), 'retake.png', scope, use_memory=False, context=retake_context)
    old_capture = pilot.get(scope.owner_id, first['pilot']['capture_id'], 'capture')
    old_review = pilot.get(scope.owner_id, review['id'], 'review')
    assert old_capture['resolved_by'] == second['pilot']['capture_id']
    assert old_review['resolved_by'] == second['pilot']['capture_id']
    assert old_review['outcome'] == 'retake'
    new_review = next(r for r in pilot.list(scope.owner_id, 'review') if r['inspection_id'] == second['id'])
    pilot.update(scope.owner_id, new_review['id'], new_review['version'],
        {'status': 'closed', 'outcome': 'accept', 'reason': 'Checked clear view.'}, actor=actor)
    lot = pilot.get(scope.owner_id, first['pilot']['lot_id'], 'lot')
    assert pilot.update(scope.owner_id, lot['id'], lot['version'], {'status': 'closed'}, actor=actor)['status'] == 'closed'


def test_report_keeps_open_prior_review_unresolved_until_human_closes_it(tmp_path):
    from fastapi import HTTPException
    from app.pilot.reports import lot_evidence
    service, pilot, actor, scope, context, _ = lane(tmp_path)
    first = service.run(png(), 'part.png', scope, use_memory=False, context=context())
    old_review = pilot.list(scope.owner_id, 'review')[0]
    retake = {**context('capture-retake', 'part-one'), 'retake_of': first['pilot']['capture_id']}
    second = service.run(png(), 'retake.png', scope, use_memory=False, context=retake)
    new_review = next(r for r in pilot.list(scope.owner_id, 'review') if r['inspection_id'] == second['id'])
    pilot.update(scope.owner_id, new_review['id'], new_review['version'],
        {'status': 'closed', 'outcome': 'accept', 'reason': 'Checked clear view.'}, actor=actor)
    lot = pilot.get(scope.owner_id, first['pilot']['lot_id'], 'lot')
    with pytest.raises(HTTPException) as pending:
        pilot.update(scope.owner_id, lot['id'], lot['version'], {'status': 'closed'}, actor=actor)
    assert pending.value.status_code == 409
    report = lot_evidence(service, scope.owner_id, lot['id'])
    assert report['counts']['unresolved_parts'] == 1
    # A completed replacement preserves the old review but does not decide it.
    old_review = pilot.get(scope.owner_id, old_review['id'], 'review')
    pilot.update(scope.owner_id, old_review['id'], old_review['version'],
        {'status': 'closed', 'outcome': 'retake', 'reason': 'Replacement reviewed.'}, actor=actor)
    assert lot_evidence(service, scope.owner_id, lot['id'])['counts']['unresolved_parts'] == 0
    assert pilot.update(scope.owner_id, lot['id'], lot['version'], {'status': 'closed'}, actor=actor)['status'] == 'closed'


def test_recovered_capture_keeps_original_actor_and_capture_time(tmp_path):
    from app.pilot.integration import reserve_capture
    service, pilot, actor, scope, context, _ = lane(tmp_path)
    reserved = context()
    reserve_capture(service.store, scope, reserved, png(), memory=False)
    # The job was never committed, and another operator resumes the reserved capture.
    retried = {**reserved, 'captured_at': '2099-01-01T00:00:00+00:00',
               'actor': {**actor, 'id': 'retrying-user', 'name': 'Another operator'}}
    result = service.run(png(), 'retry.png', scope, use_memory=False, context=retried)
    saved = pilot.get(scope.owner_id, reserved['capture_id'], 'capture')
    assert result['pilot']['actor'] == saved['context']['actor'] == actor
    assert result['pilot']['captured_at'] == saved['context']['captured_at'] == reserved['captured_at']


def test_later_capture_disposition_cannot_be_superseded_by_earlier_late_review(tmp_path):
    from app.pilot.reports import lot_evidence
    from fastapi import HTTPException
    service, pilot, actor, scope, context, _ = lane(tmp_path)
    first = service.run(png(), 'part.png', scope, use_memory=False, context=context())
    early_review = pilot.list(scope.owner_id, 'review')[0]
    second = service.run(png(), 'retake.png', scope, use_memory=False,
        context={**context('capture-retake', 'part-one'), 'retake_of': first['pilot']['capture_id']})
    later_review = next(r for r in pilot.list(scope.owner_id, 'review') if r['inspection_id'] == second['id'])
    early_review = pilot.get(scope.owner_id, early_review['id'], 'review')
    pilot.update(scope.owner_id, early_review['id'], early_review['version'],
        {'status': 'closed', 'outcome': 'accept', 'reason': 'Earlier capture accepted.'}, actor=actor)
    pilot.update(scope.owner_id, later_review['id'], later_review['version'],
        {'status': 'closed', 'outcome': 'hold', 'reason': 'Later capture needs investigation.'}, actor=actor)
    # Simulate the first assessment completing after the retake's review was created.
    from app.pilot import tables
    with pilot.engine.begin() as connection:
        connection.execute(tables.records.update().where(tables.records.c.owner_id == scope.owner_id,
            tables.records.c.id == early_review['id']).values(created_at='2099-01-01T00:00:00+00:00'))
    lot = pilot.get(scope.owner_id, first['pilot']['lot_id'], 'lot')
    assert lot_evidence(service, scope.owner_id, lot['id'])['counts']['unresolved_parts'] == 1
    with pytest.raises(HTTPException) as pending:
        pilot.update(scope.owner_id, lot['id'], lot['version'], {'status': 'closed'}, actor=actor)
    assert pending.value.status_code == 409


def test_revoked_member_cannot_receive_final_result_on_an_already_open_stream(tmp_path, monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    from starlette.requests import Request
    from app.main import app
    client, routes, form, _ = http_lane(tmp_path, monkeypatch)
    token = client.post('/api/workspace/pilot/invites', json={'role': 'operator'}).json()['token']
    member = TestClient(app)
    joined = member.post('/api/workspace/pilot/join', json={'token': token, 'username': 'stream.operator',
        'password': 'stream-operator-test-password', 'name': 'Stream operator'})
    assert joined.status_code == 201
    identity = joined.json()
    membership = next(m for m in client.get('/api/workspace/pilot/team').json()['members']
                      if m['user_id'] == identity['user']['id'])
    monkeypatch.setenv('SPECLENS_WORKER', 'external')
    job = routes.jobs.submit('inspect', {}, identity['team']['id'])

    async def exercise():
        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}
        request = Request({'type': 'http', 'method': 'GET', 'scheme': 'http', 'server': ('testserver', 80),
            'path': f'/api/workspace/jobs/{job["id"]}/events', 'query_string': b'',
            'headers': [(b'cookie', f'speclens_session={member.cookies.get("speclens_session")}'.encode())]}, receive)
        response = await routes.job_events(job['id'], request)
        stream = response.body_iterator
        first = await anext(stream)
        assert first['event'] == 'status'
        revoked = client.patch(f'/api/workspace/pilot/members/{membership["id"]}', json={
            'version': membership['version'], 'role': 'operator', 'active': False})
        assert revoked.status_code == 200, revoked.text
        routes.jobs.complete(job['id'], {'private_result': 'team evidence'})
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(anext(stream), timeout=2)
    asyncio.run(exercise())


def test_interrupted_candidate_proposal_is_repaired_by_identical_retry(tmp_path, monkeypatch):
    from app.pilot import integration
    service, pilot, actor, scope, context, observed = lane(tmp_path)
    result = service.run(png(), 'part.png', scope, use_memory=False, context=context())
    values = {'verdict': 'defect', 'defect_type': 'print',
              'rule_text': 'Reject visible ink markings.', 'reviewer': actor['name']}
    propose = integration.propose_standard
    def stopped(*args, **kwargs):
        raise RuntimeError('Process stopped before candidate commit.')
    monkeypatch.setattr(integration, 'propose_standard', stopped)
    with pytest.raises(RuntimeError, match='Process stopped'):
        service.correct(result['id'], **values)
    assert len(service.store.corrections(scope.id)) == 1
    assert pilot.list(scope.owner_id, 'standard') == []
    monkeypatch.setattr(integration, 'propose_standard', propose)
    recovered = service.correct(result['id'], **values)
    assert len(service.store.corrections(scope.id)) == 1
    standards = pilot.list(scope.owner_id, 'standard')
    assert len(standards) == 1 and standards[0]['correction_id'] == recovered['id']
    assert observed['retains'] == 0
    with pytest.raises(ValueError, match='already has a correction'):
        service.correct(result['id'], **{**values, 'rule_text': 'Different proposed rule.'})


@pytest.mark.parametrize('reason', ['exhausted_worker', 'missing_upload'])
def test_terminal_job_failure_leaves_a_durable_retakeable_capture(tmp_path, monkeypatch, reason):
    import time
    import sqlalchemy as sa
    from app import db
    from app.jobs.queue import MAX_ATTEMPTS
    from app.pilot.store import PilotStore
    client, routes, form, _ = http_lane(tmp_path, monkeypatch)
    monkeypatch.setenv('SPECLENS_WORKER', 'external')
    response = client.post('/api/workspace/jobs/inspect', data=form,
        files={'file': ('part.png', png(), 'image/png')})
    assert response.status_code == 202, response.text
    job = routes.jobs.get(response.json()['id'])
    if reason == 'exhausted_worker':
        with routes.jobs.engine.begin() as connection:
            connection.execute(db.jobs.update().where(db.jobs.c.id == job['id']).values(
                status='running', attempts=MAX_ATTEMPTS, locked_at=time.time()-3600))
        routes.jobs.recover_stale()
    else:
        routes.service.media.delete(job['payload']['upload'])
        routes.jobs.process(job['id'])
    assert routes.jobs.get(job['id'])['status'] == 'failed'
    owner = client.get('/api/workspace/pilot/session').json()['team']['id']
    pilot = PilotStore(routes.service.store.engine)
    capture = pilot.get(owner, form['capture_id'], 'capture')
    assert capture['status'] == 'failed'
    assert capture['error']
    assert any(event['target_id'] == capture['id'] and event['details'].get('status') == 'failed'
               for event in pilot.list(owner, 'event'))
    assert not pilot.list(owner, 'review')


def http_lane(tmp_path, monkeypatch):
    from test_workspace_api import setup_client
    client, routes = setup_client(tmp_path, monkeypatch)
    base = '/api/workspace/pilot'
    registration = client.post(base+'/register', json={'username': 'quality.owner', 'password': 'test-password-12345',
        'name': 'Quality owner', 'team_name': 'Pilot factory'})
    assert registration.status_code == 201, registration.text
    product = client.post(base+'/products', json={'code': 'P-01', 'name': 'Shell', 'factory': 'Factory A'}).json()
    revision = client.post(base+'/revisions', json={'product_id': product['id'], 'label': 'A',
        'spec_text': '4.1 Print: reject every ink marking.', 'capture_instructions': 'One part, top down.'}).json()
    response = client.patch(base+f'/revisions/{revision["id"]}', json={'version': revision['version'], 'status': 'approved'})
    assert response.status_code == 200, response.text
    revision = response.json()
    station = client.post(base+'/stations', json={'product_id': product['id'], 'name': 'Bench 1',
        'instructions': 'Use the fixture and fixed light.'}).json()
    lot = client.post(base+'/lots', json={'reference': 'LOT-1', 'revision_id': revision['id'],
        'station_id': station['id']}).json()
    form = {'revision_id': revision['id'], 'lot_id': lot['id'], 'station_id': station['id'],
        'physical_part_id': 'PART-1', 'capture_id': 'capture-http-one', 'memory_enabled': 'false'}
    return client, routes, form, lot


def test_controlled_http_capture_review_and_complete_lot_exports(tmp_path, monkeypatch):
    client, routes, form, lot = http_lane(tmp_path, monkeypatch)
    response = client.post('/api/workspace/inspect', data=form, files={'file': ('part.png', png(), 'image/png')})
    assert response.status_code == 200, response.text
    original = response.json()
    again = client.post('/api/workspace/inspect', data=form, files={'file': ('part.png', png(), 'image/png')})
    assert again.status_code == 200, again.text
    assert again.json()['id'] == original['id']
    overview = client.get('/api/workspace/pilot/overview').json()
    assert len(overview['captures']) == len(overview['reviews']) == 1
    review = overview['reviews'][0]
    assert client.patch(f'/api/workspace/pilot/lots/{lot["id"]}',
        json={'version': lot['version'], 'status': 'closed'}).status_code == 409
    disposition = client.patch(f'/api/workspace/pilot/reviews/{review["id"]}',
        json={'version': review['version'], 'status': 'closed', 'outcome': 'accept', 'reason': 'Checked against clause 4.1.'})
    assert disposition.status_code == 200, disposition.text
    assert routes.service.store.inspection(original['id'])['verdict'] == original['verdict']
    assert client.get('/api/workspace/pilot/overview').json()['standards'] == []
    report = client.get(f'/api/workspace/pilot/lots/{lot["id"]}/export')
    assert report.status_code == 200, report.text
    data = report.json()
    assert data['counts']['physical_parts'] == 1
    assert data['counts']['capture_attempts'] == 1
    assert data['counts']['unresolved_parts'] == 0
    assert data['inspections'][0]['id'] == original['id']
    assert data['reviews'][0]['outcome'] == 'accept'
    assert data['evidence'][0]['available'] is True
    csv = client.get(f'/api/workspace/pilot/lots/{lot["id"]}/csv')
    assert csv.status_code == 200 and 'PART-1' in csv.text and 'human_outcome' in csv.text
    assert client.patch(f'/api/workspace/pilot/lots/{lot["id"]}',
        json={'version': lot['version'], 'status': 'closed'}).status_code == 200


def test_team_identity_applies_to_old_media_jobs_history_and_delete_paths(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    client, routes, form, lot = http_lane(tmp_path, monkeypatch)
    inspection = client.post('/api/workspace/inspect', data=form,
        files={'file': ('part.png', png(), 'image/png')}).json()
    assert client.get(inspection['image_url']).status_code == 200
    other = TestClient(app)
    registered = other.post('/api/workspace/pilot/register', json={'username': 'other.owner',
        'password': 'different-test-password', 'name': 'Other', 'team_name': 'Other team'})
    assert registered.status_code == 201
    assert other.get(inspection['image_url']).status_code == 404
    assert other.get('/api/workspace/overview', params={'revision_id': form['revision_id']}).status_code == 404
    assert other.get(f'/api/workspace/pilot/lots/{lot["id"]}/export').status_code == 404
    invitation = client.post('/api/workspace/pilot/invites', json={'role': 'viewer'}).json()
    viewer = TestClient(app)
    joined = viewer.post('/api/workspace/pilot/join', json={'token': invitation['token'], 'username': 'line.viewer',
        'password': 'viewer-test-password', 'name': 'Read only'})
    assert joined.status_code == 201, joined.text
    assert viewer.get(inspection['image_url']).status_code == 200
    assert viewer.post('/api/workspace/inspect', data={**form, 'capture_id': 'capture-not-allowed'},
        files={'file': ('part.png', png(), 'image/png')}).status_code == 403
    assert viewer.request('DELETE', '/api/workspace/data', json={'confirm': 'DELETE'}).status_code == 403
    assert viewer.post('/api/workspace/corrections', json={'inspection_id': inspection['id'], 'verdict': 'good',
        'defect_type': 'good', 'rule_text': 'Natural shell texture is acceptable.', 'reviewer': 'Forged owner'}).status_code == 403


def test_failed_identical_submission_can_retry_after_provider_recovery(tmp_path, monkeypatch):
    from app.jobs.queue import JobFailed
    client, routes, form, lot = http_lane(tmp_path, monkeypatch)
    original = routes.service.inspector
    def unavailable(*args, **options):
        raise JobFailed(503, 'The inspection provider is unavailable.')
    routes.service.inspector = unavailable
    failed = client.post('/api/workspace/inspect', data=form, files={'file': ('part.png', png(), 'image/png')})
    assert failed.status_code == 503
    routes.service.inspector = original
    retry = client.post('/api/workspace/inspect', data=form, files={'file': ('part.png', png(), 'image/png')})
    assert retry.status_code == 200, retry.text
    overview = client.get('/api/workspace/pilot/overview').json()
    assert len(overview['captures']) == len(overview['reviews']) == 1
    assert overview['captures'][0]['status'] == 'done'


def test_database_only_pilot_work_does_not_consume_the_model_post_quota(tmp_path, monkeypatch):
    from app import public
    monkeypatch.setattr(public, 'PUBLIC_MODE', True)
    def no_model_calls(*args, **kwargs):
        pytest.fail('Catalog and review management must not consume the model request quota.')
    monkeypatch.setattr(public, 'allow_call', no_model_calls)
    client, routes, form, lot = http_lane(tmp_path, monkeypatch)
    assert client.get('/api/workspace/pilot/overview').status_code == 200


def test_unapproved_candidates_cannot_starve_the_memory_retry_outbox(tmp_path):
    service, pilot, actor, scope, context, observed = lane(tmp_path)
    for n in range(22):
        inspection = service.run(png(), 'part.png', scope, use_memory=False, context=context(f'capture-{n}', f'part-{n}'))
        service.correct(inspection['id'], verdict='defect', defect_type='print',
            rule_text=f'Visible ink rule number {n} requires rejection.', reviewer=actor['name'])
    standard = pilot.list(scope.owner_id, 'standard')[0]
    pilot.update(scope.owner_id, standard['id'], standard['version'], {'status': 'approved'}, actor=actor)
    assert service.drain_outbox(limit=20)['synced'] == 1
    assert observed['retains'] == 1


def test_factory_comparison_uses_approved_taxonomy_and_blocks_retired_revision(tmp_path, monkeypatch):
    client, routes, form, lot = http_lane(tmp_path, monkeypatch)
    seen = []
    def inspector(image, spec, classes, **kw):
        seen.append(classes)
        return {'verdict': 'good', 'type': 'good', 'rationale': 'No ink.', 'confidence': .8, 'ms': 1, 'cost_usd': 0}
    routes.service.inspector = inspector
    params = {'revision_id': form['revision_id']}
    revision = client.get('/api/workspace/pilot/overview').json()['revisions'][0]
    approved_classes = [c['defect_type'] for c in revision['taxonomy']['classes']]
    identity = client.get('/api/workspace/pilot/session').json()
    routes.service.save_taxonomy('4.1 Print: reject every ink marking.', {'classes': [], 'source': 'model'},
        identity['team']['id'])
    compared = client.post('/api/workspace/compare', data=params, files={'file': ('part.png', png(), 'image/png')})
    assert compared.status_code == 200, compared.text
    assert approved_classes
    assert seen == [approved_classes, approved_classes]
    assert compared.json()['baseline']['activity_kind'] == 'comparison'
    revision = client.get('/api/workspace/pilot/overview').json()['revisions'][0]
    client.patch(f'/api/workspace/pilot/revisions/{revision["id"]}',
        json={'version': revision['version'], 'status': 'retired'})
    blocked = client.post('/api/workspace/compare', data=params, files={'file': ('part.png', png(), 'image/png')})
    assert blocked.status_code == 409
    assert len(seen) == 2


def test_losing_concurrent_attempt_cannot_overwrite_winning_visual_evidence(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    import numpy as np
    service, pilot, actor, scope, context, _ = lane(tmp_path)
    both = threading.Barrier(2)
    release = threading.Event()
    lock = threading.Lock()
    calls = []
    def inspector(*args, **kwargs):
        with lock:
            index = len(calls)
            calls.append(index)
        both.wait(5)
        if index:
            assert release.wait(5)
        mask = np.zeros((80, 80), bool)
        mask[10+index*40:20+index*40, 10:20] = True
        return {'verdict': 'defect', 'defect': True, 'type': 'print', 'confidence': .9,
            'rationale': f'Attempt {index}', 'box_px': [10, 10, 20, 20], 'mask': mask, 'ms': 1, 'cost_usd': 0}
    service.inspector = inspector
    shared = context()
    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(service.run, png(), 'part.png', scope, use_memory=False, context=shared)
        two = pool.submit(service.run, png(), 'part.png', scope, use_memory=False, context=shared)
        import time
        deadline = time.monotonic()+5
        while not one.done() and not two.done():
            assert time.monotonic()<deadline
            time.sleep(.01)
        winner = (one if one.done() else two).result()
        key = winner['mask_url'].removeprefix('/files/workspace/')
        original_mask = service.media.get(key)
        release.set()
        assert one.result()['id'] == two.result()['id']
    assert service.media.get(key) == original_mask


def test_capture_submission_identity_is_independent_between_teams(tmp_path):
    from app.pilot.store import PilotStore
    from app.workspace.store import Store
    pilot = PilotStore(Store(tmp_path/'db.sqlite').engine)
    first = pilot.create('team-a', 'capture', {'physical_part_id': 'part'}, id='capture-same')
    second = pilot.create('team-b', 'capture', {'physical_part_id': 'part'}, id='capture-same')
    assert first['owner_id'] != second['owner_id']
