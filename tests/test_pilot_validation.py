"""Imported validation is a paired physical-part evaluation, never live inference."""
import copy
import importlib

import pytest
from pydantic import ValidationError


def evaluate(cases, configuration=None):
    from app.pilot.validation import ValidationImport, evaluate_validation
    body = ValidationImport(name='Frozen later-lot comparison', cases=cases,
                            configuration=configuration or {})
    return evaluate_validation(body)


def case(sample, truth='defect', baseline='good', with_memory='defect', *, part=None,
         lot='lot-a', session='session-a', **extra):
    return {'sample_id': sample, 'physical_part_id': part or sample, 'lot_id': lot,
            'session_id': session, 'truth': truth, 'baseline': baseline,
            'with_memory': with_memory, **extra}


def test_review_and_errors_do_not_count_as_correct_decisions_or_disappear_from_denominators():
    output = evaluate([
        case('d1'),
        case('d2', baseline='uncertain', with_memory='error'),
        case('d3', baseline='error', with_memory='uncertain'),
        case('g1', truth='good', baseline='defect', with_memory='good'),
        case('g2', truth='good', baseline='good', with_memory='defect'),
        case('g3', truth='good', baseline='uncertain', with_memory='good'),
    ])
    result = output['results']
    assert result['baseline']['matrix'] == {
        'good': {'good': 1, 'defect': 1, 'uncertain': 1, 'error': 0},
        'defect': {'good': 1, 'defect': 0, 'uncertain': 1, 'error': 1},
    }
    assert result['baseline']['escaped_defects'] == {'count': 1, 'denominator': 3, 'rate': 1 / 3}
    assert result['baseline']['false_rejects'] == {'count': 1, 'denominator': 3, 'rate': 1 / 3}
    assert result['baseline']['review'] == {'count': 2, 'denominator': 6, 'rate': 1 / 3}
    assert result['baseline']['errors'] == {'count': 1, 'denominator': 6, 'rate': 1 / 6}
    assert result['baseline']['decision_coverage'] == {'count': 3, 'denominator': 6, 'rate': .5}
    assert result['with_memory']['escaped_defects'] == {'count': 0, 'denominator': 3, 'rate': 0.0}
    assert result['paired']['resolved_improvements'] == 2
    assert result['paired']['resolved_regressions'] == 1
    assert result['paired']['transitions']['uncertain']['good'] == 1


def test_repeat_views_preserve_the_manifest_without_inflating_part_counts_or_uncertainty():
    first = case('first-view', part='part-1', severity='critical')
    repeat = case('second-view', part='part-1', session='session-b', severity='critical')
    rows = [first, repeat, case('part-2', lot='lot-a', session='session-b')]
    original = copy.deepcopy(rows)
    output = evaluate(rows, {'model': 'importer-supplied', 'teaching_disjoint': True})
    assert rows == original
    assert output['manifest']['cases'] == original
    assert output['manifest']['selected_sample_ids'] == ['first-view', 'part-2']
    assert output['manifest']['aggregation'] == 'first_occurrence_per_physical_part'
    assert output['manifest']['input_order_is_attempt_order'] is True
    assert output['results']['counts'] == {
        'samples': 3, 'physical_parts': 2, 'repeated_views': 1,
        'lots': 1, 'sessions': 2, 'clusters': 1, 'truth': {'good': 0, 'defect': 2},
    }
    assert output['results']['baseline']['escaped_defects']['denominator'] == 2
    assert output['results']['baseline']['false_rejects']['rate'] is None
    assert output['results']['uncertainty']['replicates'] == 0
    assert output['results']['uncertainty']['delta_rates']['escaped_defects'] == {
        'estimate': -1.0, 'lower': None, 'upper': None,
    }
    assert output['source'] == 'imported_unverified'
    assert any('unverified' in text.lower() for text in output['results']['limitations'])
    assert any('leakage' in text.lower() for text in output['results']['limitations'])


@pytest.mark.parametrize('changed', [
    {'truth': 'good'}, {'baseline': 'defect'}, {'with_memory': 'error'},
    {'lot_id': 'lot-other'}, {'severity': 'major'},
])
def test_conflicting_repeated_part_results_are_rejected_instead_of_selecting_a_favorable_retake(changed):
    rows = [case('view-1', part='same-part'), {**case('view-2', part='same-part'), **changed}]
    with pytest.raises(ValidationError, match='Repeated physical part'):
        evaluate(rows)


def test_duplicate_sample_ids_are_rejected_even_if_the_physical_parts_differ():
    with pytest.raises(ValidationError, match='Duplicate sample_id'):
        evaluate([case('same-sample', part='one'), case('same-sample', part='two')])


def test_crossed_lot_and_session_membership_forms_connected_clusters_instead_of_row_resampling():
    output = evaluate([
        case('a', lot='lot-1', session='session-1'),
        case('b', lot='lot-1', session='session-2'),
        case('c', lot='lot-2', session='session-2'),
        case('d', lot='lot-3', session='session-3', baseline='defect', with_memory='good'),
    ])
    uncertainty = output['results']['uncertainty']
    assert output['results']['counts']['clusters'] == 2
    assert sorted(len(cluster['physical_part_ids']) for cluster in output['manifest']['clusters']) == [1, 3]
    assert uncertainty['delta_rates']['escaped_defects'] == {
        'estimate': -.5, 'lower': -1.0, 'upper': 1.0,
    }
    assert uncertainty['replicates'] == 1000
    assert uncertainty['method'] == 'paired_connected_lot_session_cluster_bootstrap'
    assert any('few' in text.lower() for text in output['results']['limitations'])
    assert evaluate(output['manifest']['cases'])['results'] == output['results']


def test_manifest_hash_freezes_configuration_and_attempt_order_and_has_no_reference_aliases():
    rows = [case('view-1', part='same'), case('view-2', part='same')]
    config = {'memory_release': {'id': 'release-1'}}
    first = evaluate(rows, config)
    second = evaluate(list(reversed(rows)), config)
    third = evaluate(rows, {'memory_release': {'id': 'release-2'}})
    assert len(first['manifest']['sha256']) == 64
    assert first['manifest']['sha256'] != second['manifest']['sha256']
    assert first['manifest']['sha256'] != third['manifest']['sha256']
    config['memory_release']['id'] = 'mutated'
    rows[0]['baseline'] = 'error'
    assert first['configuration']['memory_release']['id'] == 'release-1'
    assert first['manifest']['cases'][0]['baseline'] == 'good'


def test_missing_truth_class_has_no_rate_or_interval_even_with_multiple_clusters():
    output = evaluate([
        case('good-a', truth='good', baseline='uncertain', with_memory='good', lot='a', session='a'),
        case('good-b', truth='good', baseline='error', with_memory='defect', lot='b', session='b'),
    ])
    result = output['results']
    assert result['with_memory']['escaped_defects'] == {'count': 0, 'denominator': 0, 'rate': None}
    assert result['uncertainty']['delta_rates']['escaped_defects'] == {
        'estimate': None, 'lower': None, 'upper': None,
    }
    assert result['uncertainty']['valid_replicates']['escaped_defects'] == 0
    assert result['paired']['restored_decisions'] == 2
    assert result['paired']['resolved_improvements'] == 0
    assert result['paired']['resolved_regressions'] == 0


@pytest.mark.parametrize('cases,configuration', [
    ([], {}), ([case('a', truth='uncertain')], {}),
    ([case('a', with_memory='review')], {}),
    ([case('a', physical_part_id='   ')], {}),
    ([case('a', extra_input='ignored?')], {}),
    ([case('a')], {'large': 'x' * 12001}),
    ([case('a')], {'invalid': float('nan')}),
    ([case(str(i)) for i in range(2001)], {}),
])
def test_malformed_or_unbounded_imports_are_rejected(cases, configuration):
    with pytest.raises(ValidationError):
        evaluate(cases, configuration)


def validation_client(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.workspace.store import Store
    workspace_routes = importlib.import_module('app.workspace.routes')
    pilot_routes = importlib.import_module('app.pilot.routes')
    validation_routes = importlib.import_module('app.pilot.validation_routes')
    monkeypatch.setattr(workspace_routes.service, 'store', Store(tmp_path / 'validation.sqlite'))
    app = FastAPI()
    app.include_router(pilot_routes.router)
    app.include_router(validation_routes.router)
    return TestClient(app)


def register(client, username='validator', team_name='Quality team'):
    response = client.post('/api/workspace/pilot/register', json={
        'username': username, 'password': 'factory-test-password-123',
        'name': username.title(), 'team_name': team_name,
    })
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_validation_runs_are_durable_immutable_team_owned_records_and_activity(tmp_path, monkeypatch):
    client = validation_client(tmp_path, monkeypatch)
    assert client.get('/api/workspace/pilot/validation').status_code == 401
    session = register(client)
    payload = {'name': 'Later lot', 'cases': [case('sample-a')], 'configuration': {'model': 'imported'}}
    response = client.post('/api/workspace/pilot/validation', json=payload)
    assert response.status_code == 201, response.text
    run = response.json()
    assert run['kind'] == 'validation'
    assert run['owner_id'] == session['team']['id']
    assert run['version'] == 1
    assert client.get('/api/workspace/pilot/validation').json() == {'runs': [run]}
    assert client.patch(f"/api/workspace/pilot/validation/{run['id']}", json={'version': 1, 'name': 'changed'}).status_code in (404, 405)
    from app.pilot.store import PilotStore
    from app.workspace.routes import service
    reopened = PilotStore(service.store.engine)
    assert reopened.get(session['team']['id'], run['id'], kind='validation') == run
    events = reopened.list(session['team']['id'], 'event')
    assert any(event['target_id'] == run['id'] for event in events)
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        reopened.update(session['team']['id'], run['id'], 1, {'manifest': {}})
    assert error.value.status_code == 409
    assert reopened.get(session['team']['id'], run['id']) == run
    assert reopened.list(session['team']['id'], 'event') == events
    client.post('/api/workspace/pilot/logout')
    register(client, username='other-validator', team_name='Other team')
    assert client.get('/api/workspace/pilot/validation').json() == {'runs': []}


@pytest.mark.parametrize('role,allowed', [('viewer', False), ('operator', False), ('engineer', True)])
def test_validation_import_uses_same_team_role_policy_as_quality_changes(tmp_path, monkeypatch, role, allowed):
    client = validation_client(tmp_path, monkeypatch)
    register(client)
    invite = client.post('/api/workspace/pilot/invites', json={'role': role})
    assert invite.status_code in (200, 201), invite.text
    client.post('/api/workspace/pilot/logout')
    joined = client.post('/api/workspace/pilot/join', json={
        'token': invite.json()['token'], 'username': f'validation-{role}',
        'password': 'factory-test-password-123', 'name': role.title(),
    })
    assert joined.status_code in (200, 201), joined.text
    assert client.get('/api/workspace/pilot/validation').status_code == 200
    response = client.post('/api/workspace/pilot/validation', json={'name': 'Imported', 'cases': [case('a')]})
    assert response.status_code == (201 if allowed else 403), response.text


def test_invalid_import_creates_no_validation_or_activity_record(tmp_path, monkeypatch):
    client = validation_client(tmp_path, monkeypatch)
    register(client)
    before = client.get('/api/workspace/pilot/overview').json()['activity']
    response = client.post('/api/workspace/pilot/validation', json={
        'name': 'Conflicting inputs', 'cases': [case('a'), case('a')],
    })
    assert response.status_code == 422
    assert client.get('/api/workspace/pilot/validation').json() == {'runs': []}
    assert client.get('/api/workspace/pilot/overview').json()['activity'] == before
