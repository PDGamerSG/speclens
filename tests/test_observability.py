"""Every response carries a request ID, logs can be JSON, and a queued job keeps the ID of its request."""
import json
import logging

from app.observability import JsonFormatter, RequestIdFilter, request_id
from test_workspace_api import setup_client


def test_responses_carry_a_request_id_and_keep_a_valid_incoming_one(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    fresh = client.get('/healthz').headers['x-request-id']
    assert len(fresh) == 32
    assert client.get('/healthz', headers={'X-Request-ID': 'vercel-abc12345'}).headers['x-request-id'] == 'vercel-abc12345'
    assert client.get('/healthz', headers={'X-Request-ID': 'bad id<script>'}).headers['x-request-id'] != 'bad id<script>'


def test_a_queued_job_remembers_the_request_that_created_it(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    job = client.post('/api/workspace/jobs/inspect', headers={'X-Request-ID': 'trace-12345678'},
                      data={'sample_id': 'white-print', 'memory_enabled': 'false'}).json()
    assert routes.jobs.get(job['id'])['payload']['request_id'] == 'trace-12345678'


def test_json_log_lines_include_the_request_id():
    record = logging.LogRecord('speclens.test', logging.INFO, __file__, 1, 'Inspected %s', ('insp-1',), None)
    token = request_id.set('trace-12345678')
    try:
        RequestIdFilter().filter(record)
    finally:
        request_id.reset(token)
    line = json.loads(JsonFormatter().format(record))
    assert line['message'] == 'Inspected insp-1'
    assert line['request_id'] == 'trace-12345678'
    assert line['level'] == 'INFO'
