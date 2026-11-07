"""Public visitors must not read or teach one another's inspection memory."""
import asyncio

import httpx
from fastapi.testclient import TestClient

from test_workspace_api import setup_client


def public_clients(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    import app.public as public
    from app.main import app
    monkeypatch.setattr(public, 'PUBLIC_MODE', True)
    public.limiter.clear()
    return client, TestClient(app), routes


def test_public_visitors_keep_their_own_records_and_corrections(tmp_path, monkeypatch):
    first, second, routes = public_clients(tmp_path, monkeypatch)
    item = first.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'}).json()
    assert first.get('/api/workspace/overview').json()['stats']['inspections'] == 1
    assert second.get('/api/workspace/overview').json()['stats']['inspections'] == 0
    assert first.get(item['image_url']).status_code == 200
    assert second.get(item['image_url']).status_code == 404
    values = {'inspection_id': item['id'], 'verdict': 'defect', 'defect_type': 'print',
              'rule_text': 'Sharp white letters are ink markings.', 'reviewer': 'QA'}
    assert second.post('/api/workspace/corrections', json=values).status_code == 404
    saved = first.post('/api/workspace/corrections', json=values).json()
    assert saved['sync_status'] == 'synced'
    assert second.post(f'/api/workspace/corrections/{saved["id"]}/sync').status_code == 404
    assert second.get('/api/workspace/overview').json()['corrections'] == []


def test_public_memory_banks_follow_the_visitor_on_retain_and_recall(tmp_path, monkeypatch):
    first, second, routes = public_clients(tmp_path, monkeypatch)
    from app.workspace.memory import HindsightMemory
    calls = []
    def respond(req):
        calls.append(req.url.path)
        return httpx.Response(200, json={'success': True, 'results': []})
    routes.service.memory = HindsightMemory('https://memory.example', transport=httpx.MockTransport(respond))
    item = first.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'}).json()
    first.post('/api/workspace/corrections', json={'inspection_id': item['id'], 'verdict': 'defect',
        'defect_type': 'print', 'rule_text': 'Reject all sharp printed characters.', 'reviewer': 'QA'})
    first.post('/api/workspace/recall', json={})
    second.post('/api/workspace/recall', json={})
    banks = [url.split('/')[4] for url in calls]
    assert banks[0] == banks[1]
    assert banks[1] != banks[2]
    assert first.get('/api/workspace/overview').json()['bank_id'] == banks[0]


def test_public_mode_disables_unused_expensive_routes_and_limits_calls(tmp_path, monkeypatch):
    first, _, _ = public_clients(tmp_path, monkeypatch)
    import app.public as public
    assert first.post('/api/runs', json={}).status_code == 404
    assert first.get('/api/ledger').status_code == 404
    monkeypatch.setattr(public, 'CALL_LIMIT', 2)
    assert first.post('/api/workspace/reflect', json={}).status_code == 503
    assert first.post('/api/workspace/reflect', json={}).status_code == 503
    response = first.post('/api/workspace/reflect', json={})
    assert response.status_code == 429
    assert 'retry-after' in response.headers


def test_public_cross_origin_writes_are_rejected(tmp_path, monkeypatch):
    first, _, _ = public_clients(tmp_path, monkeypatch)
    response = first.post('/api/workspace/recall', json={}, headers={'Origin': 'https://another-site.example'})
    assert response.status_code == 403


def test_public_proxy_accepts_only_the_configured_frontend_origin(tmp_path, monkeypatch):
    first, _, _ = public_clients(tmp_path, monkeypatch)
    monkeypatch.setenv('SPECLENS_ALLOWED_ORIGINS', ' https://speclens.pallabdas.me, https://speclens-lake.vercel.app ')
    response = first.post('/api/workspace/inspect',
        data={'sample_id': 'white-print', 'memory_enabled': 'false'},
        headers={'Origin': 'https://speclens.pallabdas.me'})
    assert response.status_code == 200
    assert first.get(response.json()['image_url']).status_code == 200
    assert first.get('/api/workspace/overview').json()['stats']['inspections'] == 1


def test_public_proxy_origin_configuration_does_not_allow_lookalike_hosts(tmp_path, monkeypatch):
    first, _, _ = public_clients(tmp_path, monkeypatch)
    monkeypatch.setenv('SPECLENS_ALLOWED_ORIGINS', 'https://speclens.pallabdas.me,https://speclens-lake.vercel.app')
    for origin in ['https://speclens.pallabdas.me.attacker.example',
                   'https://another-project.vercel.app', 'http://speclens.pallabdas.me']:
        response = first.post('/api/workspace/inspect',
            data={'sample_id': 'white-print', 'memory_enabled': 'false'}, headers={'Origin': origin})
        assert response.status_code == 403
    assert first.get('/api/workspace/overview').json()['stats']['inspections'] == 0


def test_public_cookie_is_http_only_and_private_files_stay_blocked(tmp_path, monkeypatch):
    first, _, _ = public_clients(tmp_path, monkeypatch)
    response = first.get('/')
    assert 'HttpOnly' in response.headers['set-cookie']
    assert 'SameSite=lax' in response.headers['set-cookie']
    assert first.get('/files/speclens.sqlite3').status_code == 404
    assert first.get('/files/runs/anything.json').status_code == 404
    assert response.headers['x-content-type-options'] == 'nosniff'


def test_public_https_cookies_are_secure_and_survive_new_client_sessions(tmp_path, monkeypatch):
    public_clients(tmp_path, monkeypatch)
    from app.main import app
    with TestClient(app, base_url='https://speclens.example') as first:
        response = first.get('/api/workspace/status')
        assert 'Secure' in response.headers['set-cookie']
        item = first.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'}).json()
        with TestClient(app, base_url='https://speclens.example', cookies=first.cookies) as reopened:
            assert reopened.get(item['image_url']).status_code == 200
            assert reopened.get('/api/workspace/overview').json()['stats']['inspections'] == 1


def test_public_ip_limit_cannot_be_reset_with_new_browser_cookies(tmp_path, monkeypatch):
    first, _, _ = public_clients(tmp_path, monkeypatch)
    import app.public as public
    monkeypatch.setattr(public, 'CALL_LIMIT', 1)
    for _ in range(4):
        first.cookies.clear()
        assert first.post('/api/workspace/reflect', json={}).status_code == 503
    first.cookies.clear()
    assert first.post('/api/workspace/reflect', json={}).status_code == 429


def test_exported_owner_identifier_cannot_be_used_as_a_visitor_cookie(tmp_path, monkeypatch):
    first, second, _ = public_clients(tmp_path, monkeypatch)
    from app.public import COOKIE
    item = first.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'}).json()
    assert item['owner_id'] != first.cookies.get(COOKIE)
    second.cookies.set(COOKIE, item['owner_id'])
    assert second.get('/api/workspace/overview').json()['stats']['inspections'] == 0
    assert second.get(item['image_url']).status_code == 404


def test_chunked_upload_stops_at_the_public_body_limit(tmp_path, monkeypatch):
    public_clients(tmp_path, monkeypatch)
    from app.main import app
    received = 0

    async def body():
        nonlocal received
        yield b'--photo\r\nContent-Disposition: form-data; name="file"; filename="photo.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'
        for _ in range(16):
            received += 1024 * 1024
            yield b'x' * (1024 * 1024)
        yield b'\r\n--photo--\r\n'

    async def upload():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://speclens.example') as client:
            return await client.post('/api/workspace/inspect', content=body(),
                headers={'Content-Type': 'multipart/form-data; boundary=photo'})

    response = asyncio.run(upload())
    assert response.status_code == 413
    assert received <= 10 * 1024 * 1024


def test_renamed_cookie_keeps_existing_visitor_records(tmp_path, monkeypatch):
    import hashlib
    first, _, _ = public_clients(tmp_path, monkeypatch)
    legacy = 'a' * 64
    first.cookies.set('chief_skill_workspace', legacy, domain='testserver.local', path='/')
    response = first.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'})
    assert response.status_code == 200
    assert first.cookies.get('speclens_workspace') == legacy
    assert first.cookies.get('chief_skill_workspace') is None
    item = response.json()
    assert item['owner_id'] == hashlib.sha256(legacy.encode()).hexdigest()
    assert first.get(item['image_url']).status_code == 200
    assert first.get('/api/workspace/overview').json()['stats']['inspections'] == 1


def test_invalid_new_cookie_falls_back_to_valid_legacy_session(tmp_path, monkeypatch):
    first, _, _ = public_clients(tmp_path, monkeypatch)
    legacy = 'b' * 64
    first.cookies.set('chief_skill_workspace', legacy, domain='testserver.local', path='/')
    first.cookies.set('speclens_workspace', 'invalid', domain='testserver.local', path='/')
    first.get('/api/workspace/status')
    assert first.cookies.get('speclens_workspace') == legacy
