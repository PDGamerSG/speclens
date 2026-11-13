"""Visitors can export and delete their data, and old records are purged with their photos and memory."""
import json

import httpx

from app.workspace.memory import HindsightMemory
from test_public_workspace import public_clients


def recording_memory(calls):
    def respond(request):
        calls.append((request.method, request.url.path))
        if request.url.path.endswith('/memories'):
            return httpx.Response(200, json={'success': True, 'items_count': 1})
        if request.method == 'DELETE':
            return httpx.Response(200, json={'success': True})
        return httpx.Response(200, json={'results': []})
    return HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(respond))


def teach(client):
    item = client.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'}).json()
    saved = client.post('/api/workspace/corrections', json={
        'inspection_id': item['id'], 'verdict': 'defect', 'defect_type': 'print',
        'rule_text': 'Sharp white letters are ink markings.', 'reviewer': 'QA'}).json()
    return item, saved


def test_a_visitor_exports_only_their_own_records(tmp_path, monkeypatch):
    first, second, routes = public_clients(tmp_path, monkeypatch)
    calls = []
    routes.service.memory = recording_memory(calls)
    item, saved = teach(first)
    teach(second)
    export = first.get('/api/workspace/export')
    assert export.status_code == 200
    assert 'attachment' in export.headers['content-disposition']
    data = json.loads(export.content)
    assert [i['id'] for i in data['inspections']] == [item['id']]
    assert [c['id'] for c in data['corrections']] == [saved['id']]
    assert data['inspections'][0]['spec_text']


def test_deleting_my_data_removes_records_photos_and_memory_banks_but_not_other_visitors(tmp_path, monkeypatch):
    first, second, routes = public_clients(tmp_path, monkeypatch)
    calls = []
    routes.service.memory = recording_memory(calls)
    item, saved = teach(first)
    other, _ = teach(second)
    assert first.request('DELETE', '/api/workspace/data', json={'confirm': 'yes'}).status_code == 422
    result = first.request('DELETE', '/api/workspace/data', json={'confirm': 'DELETE'})
    assert result.status_code == 200
    assert result.json()['inspections'] == 1 and result.json()['corrections'] == 1
    assert result.json()['memory_failed'] == 0
    assert first.get('/api/workspace/overview').json()['stats']['inspections'] == 0
    assert first.get(item['image_url']).status_code == 404
    assert routes.service.media.get(f'{item["id"]}.jpg') is None
    assert ('DELETE', f'/v1/default/banks/speclens-{item["scope_id"]}') in calls
    assert second.get('/api/workspace/overview').json()['stats']['inspections'] == 1
    assert routes.service.media.get(f'{other["id"]}.jpg') is not None


def test_purge_removes_only_records_past_retention_and_forgets_their_memory(tmp_path, monkeypatch):
    first, _, routes = public_clients(tmp_path, monkeypatch)
    calls = []
    routes.service.memory = recording_memory(calls)
    old, old_correction = teach(first)
    recent, _ = teach(first)
    from app import db
    with routes.service.store.engine.begin() as c:
        c.execute(db.inspections.update().where(db.inspections.c.id == old['id']).values(created_at='2020-01-01T00:00:00+00:00'))
    summary = routes.service.purge(90)
    assert summary['inspections'] == 1 and summary['corrections'] == 1
    assert routes.service.store.inspection(old['id']) is None
    assert routes.service.store.inspection(recent['id']) is not None
    assert routes.service.media.get(f'{old["id"]}.jpg') is None
    assert ('DELETE', f'/v1/default/banks/speclens-{old["scope_id"]}/documents/{old_correction["id"]}') in calls
