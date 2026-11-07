"""Workspace HTTP boundary: validated photos, paired runs and a durable correction."""
import importlib
import io

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image


def setup_client(tmp_path, monkeypatch):
    routes = importlib.import_module('app.workspace.routes')
    from app.main import app
    from app.workspace.store import Store
    from app.workspace.memory import HindsightMemory
    from app.workspace.service import WorkspaceService
    def inspector(img, spec, types, **kw):
        return {'verdict': 'good', 'defect': False, 'type': 'good', 'confidence': 0.8,
                'rationale': 'Natural texture.', 'box_px': None, 'mask': None, 'ms': 1, 'cost_usd': 0.001}
    memory = HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={'success': True, 'items_count': 1}) if req.url.path.endswith('/memories') else httpx.Response(200, json={'results': []})))
    svc = WorkspaceService(Store(tmp_path / 'db.sqlite'), memory, inspector=inspector, media_root=tmp_path / 'images')
    monkeypatch.setattr(routes, 'service', svc)
    monkeypatch.setattr(routes, 'API_KEY', 'test-only')
    return TestClient(app), routes


def png():
    b = io.BytesIO()
    Image.new('RGB', (100, 100)).save(b, 'PNG')
    return b.getvalue()


def test_inspect_correct_and_reload_over_http(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    response = client.post('/api/workspace/inspect', files={'file': ('part.png', png(), 'image/png')},
                           data={'memory_enabled': 'false'})
    assert response.status_code == 200
    result = response.json()
    correction = client.post('/api/workspace/corrections', json={
        'inspection_id': result['id'], 'verdict': 'defect', 'defect_type': 'print',
        'rule_text': 'Sharp white letters are ink, not gloss.', 'reviewer': 'Anika'})
    assert correction.status_code == 201
    assert correction.json()['sync_status'] == 'synced'
    overview = client.get('/api/workspace/overview').json()
    assert overview['stats']['inspections'] == 1
    assert overview['stats']['corrections'] == 1
    assert overview['corrections'][0]['original_rationale'] == 'Natural texture.'


def test_non_image_upload_is_rejected_before_inference(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    r = client.post('/api/workspace/inspect', files={'file': ('part.png', b'not an image', 'image/png')})
    assert r.status_code == 400


@pytest.mark.parametrize('animated', [False, True])
def test_only_supported_still_photos_can_reach_inference(tmp_path, monkeypatch, animated):
    client, _ = setup_client(tmp_path, monkeypatch)
    data = io.BytesIO()
    first = Image.new('RGB', (20, 20), 'red')
    if animated:
        first.save(data, 'PNG', save_all=True, append_images=[Image.new('RGB', (20, 20), 'blue')], duration=100)
    else:
        first.save(data, 'GIF')
    response = client.post('/api/workspace/inspect', files={'file': ('photo.png', data.getvalue(), 'image/png')})
    assert response.status_code == 400
    assert 'still' in response.json()['detail'].lower() or 'jpg' in response.json()['detail'].lower()


def test_unknown_sample_and_blank_rule_are_rejected(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    assert client.post('/api/workspace/inspect', data={'sample_id': '../../.env'}).status_code == 404
    r = client.post('/api/workspace/corrections', json={'inspection_id': 'x', 'verdict': 'good',
        'defect_type': 'good', 'rule_text': '          ', 'reviewer': 'A'})
    assert r.status_code == 422


def test_padded_short_corrections_are_rejected_before_lookup(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    r = client.post('/api/workspace/corrections', json={'inspection_id': 'x', 'verdict': 'good',
        'defect_type': 'good', 'rule_text': '          x          ', 'reviewer': 'QA'})
    assert r.status_code == 422


def test_api_does_not_label_an_inspection_live_without_a_model_key(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    monkeypatch.setattr(routes, 'API_KEY', '')
    r = client.post('/api/workspace/inspect', files={'file': ('part.png', png(), 'image/png')})
    assert r.status_code == 503
    assert 'MODEL_API_KEY' in r.json()['detail']


def test_internal_database_files_are_not_downloadable(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    from app.config import VAR
    private = VAR / 'private-store-probe.sqlite'
    private.write_bytes(b'private quality records')
    try:
        r = client.get('/files/private-store-probe.sqlite')
        assert r.status_code == 404
    finally:
        private.unlink(missing_ok=True)


def test_frontend_asset_paths_cannot_escape_the_build_directory(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    from app.main import _dist
    import os
    from urllib.parse import quote
    private = tmp_path / 'private-credential-probe.txt'
    private.write_text('private server credential probe')
    relative = os.path.relpath(private, _dist)
    r = client.get('/' + quote(relative, safe=''))
    assert r.status_code == 404
    assert 'private server credential probe' not in r.text


def test_sample_provenance_is_preserved_without_guessing_for_uploads(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    def inspect_sample(id):
        r = client.post('/api/workspace/inspect', data={'sample_id': id, 'memory_enabled': 'false'})
        assert r.status_code == 200
        return r.json()
    natural = inspect_sample('natural-shell')
    marked = inspect_sample('white-print')
    assert marked['source_kind'] == 'synthetic_sample'
    assert marked['source_group'] == natural['source_group']
    uploaded = client.post('/api/workspace/inspect', files={'file': ('white-print.jpg', png(), 'image/png')},
                           data={'memory_enabled': 'false'}).json()
    assert uploaded['source_kind'] == 'upload'
    assert uploaded['source_group'] is None
    assert uploaded['sample_id'] is None
