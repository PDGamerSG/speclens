"""A correction that could not reach Hindsight is retried automatically, with backoff, until it syncs."""
import time

import httpx

from app import db
from app.workspace.memory import HindsightMemory
from app.workspace.service import WorkspaceService, sync_backoff
from app.workspace.store import Store
from test_workspace import add_inspection, scope


def service(tmp_path, responses):
    def respond(request):
        code = responses.pop(0)
        return httpx.Response(code, json={'success': code == 200, 'items_count': 1})
    memory = HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(respond))
    return WorkspaceService(Store(tmp_path / 'outbox.sqlite3'), memory, media_root=tmp_path / 'media')


def make_due(svc):
    with svc.store.engine.begin() as c:
        c.execute(db.corrections.update().values(next_sync_at=0))


def test_the_outbox_retries_a_failed_sync_after_its_backoff(tmp_path):
    svc = service(tmp_path, [503, 503, 200])
    add_inspection(svc.store, scope())
    correction = svc.correct('i-one', verdict='defect', defect_type='print', rule_text='Reject ink.', reviewer='QA')
    assert correction['sync_status'] == 'pending'
    assert svc.drain_outbox() == {'synced': 0, 'pending': 0}, 'nothing is due before the backoff ends'
    make_due(svc)
    assert svc.drain_outbox() == {'synced': 0, 'pending': 1}
    make_due(svc)
    assert svc.drain_outbox() == {'synced': 1, 'pending': 0}
    assert svc.store.correction(correction['id'])['sync_status'] == 'synced'
    make_due(svc)
    assert svc.drain_outbox() == {'synced': 0, 'pending': 0}, 'a synced correction leaves the outbox'


def test_a_failed_sync_is_scheduled_one_minute_out_then_doubles():
    assert [sync_backoff(n) for n in range(5)] == [60, 60, 120, 240, 480]
    assert sync_backoff(30) == 6 * 3600


def test_the_next_attempt_time_follows_the_backoff(tmp_path):
    svc = service(tmp_path, [503])
    add_inspection(svc.store, scope())
    before = time.time()
    correction = svc.correct('i-one', verdict='defect', defect_type='print', rule_text='Reject ink.', reviewer='QA')
    with svc.store.engine.connect() as c:
        next_at = c.execute(db.corrections.select().where(db.corrections.c.id == correction['id'])).one().next_sync_at
    assert before + 59 <= next_at <= time.time() + 61
