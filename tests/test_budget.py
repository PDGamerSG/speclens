"""The spend budget holds under parallel calls: a call reserves its cost before it starts.

With SPECLENS_TEST_DATABASE_URL set, these tests also run on Postgres. They reset its budget and model call
history, so that URL must point at a disposable database.
"""
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import db
from app.meta import ledger

TARGETS = ['sqlite'] + (['postgres'] if os.environ.get('SPECLENS_TEST_DATABASE_URL') else [])


@pytest.fixture(params=TARGETS)
def fresh(request, tmp_path, monkeypatch):
    monkeypatch.setattr(ledger, 'LEDGER', tmp_path / 'none.jsonl')
    monkeypatch.setattr(ledger, 'BUDGET_USD', 1.0)
    if request.param == 'sqlite':
        monkeypatch.setattr(ledger, 'TARGET', tmp_path / 'budget.sqlite3')
    else:
        url = os.environ['SPECLENS_TEST_DATABASE_URL']
        monkeypatch.setattr(ledger, 'TARGET', url)
        with db.engine(url).begin() as c:
            c.execute(db.model_calls.delete())
            c.execute(db.budget.update().values(spent_usd=0, reserved_usd=0, prompt_tokens=0, cached_tokens=0,
                                                saved_usd=0, imported_ledger=True))
    return ledger


def test_a_reservation_is_released_and_the_actual_cost_recorded(fresh):
    with fresh.reserve(0.4):
        assert fresh.reserved() == 0.4
        fresh.record('muse-spark-1.3', 'inspect', 5, 200, 0.05)
    assert fresh.reserved() == 0
    assert fresh.spent() == 0.05


def test_a_failed_call_still_releases_its_reservation(fresh):
    with pytest.raises(RuntimeError):
        with fresh.reserve(0.4):
            raise RuntimeError('model outage')
    assert fresh.reserved() == 0


def test_parallel_calls_cannot_reserve_past_the_budget(fresh):
    gate = threading.Barrier(8)
    admitted, refused = [], []

    def call(i):
        gate.wait()
        try:
            with fresh.reserve(0.3):
                admitted.append(i)
                time.sleep(0.2)
                fresh.record('muse-spark-1.3', 'inspect', 5, 200, 0.3)
        except fresh.BudgetExceeded:
            refused.append(i)

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(call, range(8)))
    assert len(admitted) == 3, 'three holds of $0.30 fit in $1.00, a fourth would not'
    assert len(refused) == 5
    assert fresh.spent() == 0.9


def test_daily_rollup_groups_calls_by_utc_day(fresh):
    fresh.record('muse-spark-1.3', 'inspect', 5, 200, 0.01, prompt_tokens=100, cached_tokens=40)
    fresh.record('muse-spark-1.3', 'inspect', 5, 200, 0.02, prompt_tokens=100, cached_tokens=60)
    today = time.strftime('%Y-%m-%d', time.gmtime())
    assert fresh.daily(time.time() - 3600) == [
        {'day': today, 'calls': 2, 'cost_usd': 0.03, 'prompt_tokens': 200, 'cached_tokens': 100}]
