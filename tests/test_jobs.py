"""Inspections can run on a separate worker: queued in the database, claimed once, retried, and never lost."""
import os
import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.jobs.queue import JobFailed, JobQueue
from app.worker import Worker
from app.workspace.memory import MemoryUnavailable
from test_workspace_api import png, setup_client


TARGETS = ['sqlite'] + (['postgres'] if os.environ.get('SPECLENS_TEST_DATABASE_URL') else [])


def queue(tmp_path, runner=None, target='sqlite'):
    from app import db
    engine = db.engine(tmp_path / 'jobs.sqlite3' if target == 'sqlite' else os.environ['SPECLENS_TEST_DATABASE_URL'])
    return JobQueue(lambda: engine, runner)


@pytest.mark.parametrize('target', TARGETS)
def test_a_job_is_claimed_by_one_worker_only(tmp_path, monkeypatch, target):
    monkeypatch.setenv('SPECLENS_WORKER', 'external')
    q = queue(tmp_path, target=target)
    # Earlier runs on a shared Postgres may have left queued jobs; finish them so only this job is claimable.
    while (old := q.claim()) is not None:
        q.complete(old['id'], {})
    job = q.submit('inspect', {'x': 1}, 'owner')
    claims = []
    barrier = threading.Barrier(6)

    def claim():
        barrier.wait()
        claims.append(q.claim())

    threads = [threading.Thread(target=claim) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [c['id'] for c in claims if c] == [job['id']]
    assert q.get(job['id'])['status'] == 'running'


def test_a_retryable_failure_waits_then_runs_again_and_gives_up_after_three_tries(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECLENS_WORKER', 'external')

    def flaky(job):
        raise JobFailed(502, 'Model outage', retryable=True)

    q = queue(tmp_path, flaky)
    job = q.submit('inspect', {}, 'owner')
    assert q.process()['status'] == 'queued'
    assert q.claim() is None, 'a retry waits for its backoff'
    for attempt in (2, 3):
        with q.engine.begin() as c:
            from app import db
            c.execute(db.jobs.update().values(run_after=0))
        result = q.process()
        assert result['attempts'] == attempt
    assert result['status'] == 'failed'
    assert result['error'] == {'status_code': 502, 'detail': 'Model outage'}


def test_a_job_left_running_by_a_dead_worker_is_recovered(tmp_path, monkeypatch):
    monkeypatch.setenv('SPECLENS_WORKER', 'external')
    q = queue(tmp_path)
    job = q.submit('inspect', {}, 'owner')
    q.claim()
    from app import db
    with q.engine.begin() as c:
        c.execute(db.jobs.update().values(locked_at=time.time() - 3600))
    assert q.recover_stale() == 1
    assert q.get(job['id'])['status'] == 'queued'


def worker_thread(routes, stop):
    worker = Worker(routes.jobs, routes.service, concurrency=1)

    def loop():
        while not stop.is_set():
            if not worker.run_one():
                time.sleep(0.05)

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    return thread


def test_with_an_external_worker_the_api_waits_for_the_job_and_answers_as_before(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    monkeypatch.setenv('SPECLENS_WORKER', 'external')
    called_in = []
    inner = routes.service.inspector

    def inspector(*args, **kwargs):
        called_in.append(threading.current_thread().name)
        return inner(*args, **kwargs)

    routes.service.inspector = inspector
    stop = threading.Event()
    worker_thread(routes, stop)
    try:
        response = client.post('/api/workspace/inspect', files={'file': ('part.png', png(), 'image/png')},
                               data={'memory_enabled': 'false'})
        compare = client.post('/api/workspace/compare', data={'sample_id': 'white-print', 'expected_verdict': 'defect'})
    finally:
        stop.set()
    assert response.status_code == 200
    assert response.json()['id'].startswith('insp-')
    assert compare.status_code == 200
    assert compare.json()['with_memory']['memory_enabled'] is True
    assert called_in and all(name != 'MainThread' for name in called_in)
    assert client.get('/api/workspace/overview').json()['stats']['inspections'] == 3
    assert list((tmp_path / 'images' / 'uploads').iterdir()) == [], 'finished jobs remove their upload'


def test_a_failed_job_returns_the_same_error_the_synchronous_route_would(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    monkeypatch.setenv('SPECLENS_WORKER', 'external')

    def no_memory(*args, **kwargs):
        raise MemoryUnavailable('Hindsight could not complete this request. Check the memory connection and retry.')

    routes.service.inspector = no_memory
    stop = threading.Event()
    worker_thread(routes, stop)
    try:
        response = client.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'})
    finally:
        stop.set()
    assert response.status_code == 503
    assert 'Hindsight' in response.json()['detail']


def test_queued_inspection_returns_at_once_and_streams_its_result(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    queued = client.post('/api/workspace/jobs/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'})
    assert queued.status_code == 202
    job = queued.json()
    assert set(job) == {'id', 'kind', 'batch_id', 'status', 'result', 'error', 'attempts', 'created_at'}
    deadline = time.time() + 5
    while (current := client.get(f'/api/workspace/jobs/{job["id"]}').json())['status'] != 'done':
        assert time.time() < deadline
        time.sleep(0.05)
    assert current['result']['sample_id'] == 'white-print'
    events = client.get(f'/api/workspace/jobs/{job["id"]}/events').text
    assert 'event: done' in events
    assert current['result']['id'] in events


def test_one_visitor_cannot_read_another_visitors_job(tmp_path, monkeypatch):
    from test_public_workspace import public_clients
    first, second, routes = public_clients(tmp_path, monkeypatch)
    job = first.post('/api/workspace/jobs/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'}).json()
    assert first.get(f'/api/workspace/jobs/{job["id"]}').status_code == 200
    assert second.get(f'/api/workspace/jobs/{job["id"]}').status_code == 404
    assert second.get(f'/api/workspace/jobs/{job["id"]}/events').status_code == 404
