"""A batch is several queued inspections that share a batch ID, read back together by their owner."""
import time

from test_workspace_api import png, setup_client


def wait_for(client, batch_id):
    deadline = time.time() + 10
    while not (batch := client.get(f'/api/workspace/batches/{batch_id}').json())['finished']:
        assert time.time() < deadline
        time.sleep(0.05)
    return batch


def test_a_batch_runs_every_photo_and_reports_them_together(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    batch_id = 'batch-0123456789abcdef'
    for name in ('a.png', 'b.png', 'c.png'):
        queued = client.post('/api/workspace/jobs/inspect', files={'file': (name, png(), 'image/png')},
                             data={'memory_enabled': 'false', 'batch_id': batch_id})
        assert queued.status_code == 202
        assert queued.json()['batch_id'] == batch_id
    batch = wait_for(client, batch_id)
    assert batch['counts']['done'] == 3
    assert sorted(j['filename'] for j in batch['jobs']) == ['a.png', 'b.png', 'c.png']
    assert all(j['result']['verdict'] == 'good' for j in batch['jobs'])


def test_batch_ids_are_checked_and_private(tmp_path, monkeypatch):
    from test_public_workspace import public_clients
    first, second, _ = public_clients(tmp_path, monkeypatch)
    assert first.post('/api/workspace/jobs/inspect', data={'sample_id': 'white-print', 'batch_id': '../x'}).status_code == 422
    first.post('/api/workspace/jobs/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false',
                                                     'batch_id': 'batch-aaaaaaaaaaaa'})
    assert wait_for(first, 'batch-aaaaaaaaaaaa')['counts']['done'] == 1
    assert second.get('/api/workspace/batches/batch-aaaaaaaaaaaa').status_code == 404
