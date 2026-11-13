"""Benchmark numbers are computed honestly: flagged parts, paired intervals, and a held-out split by source photo."""
import importlib.util
from pathlib import Path

from fastapi.testclient import TestClient

from app.bench import binary_metrics, paired_bootstrap

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'benchmark.py'


def rows(pairs):
    return [{'expected': e, 'verdict': v} for e, v in pairs]


def test_review_counts_as_flagged_and_metrics_follow_the_confusion_matrix():
    m = binary_metrics(rows([('defect', 'defect'), ('defect', 'uncertain'), ('defect', 'good'),
                             ('good', 'good'), ('good', 'defect')]))
    assert (m['tp'], m['fn'], m['fp'], m['tn']) == (2, 1, 1, 1)
    assert m['precision'] == 2 / 3 and m['recall'] == 2 / 3
    assert round(m['f1'], 4) == round(2 / 3, 4)
    assert m['review_rate'] == 0.2


def test_the_paired_interval_is_reproducible_and_contains_the_point_estimate():
    off = rows([('defect', 'good')] * 4 + [('good', 'good')] * 6)
    on = rows([('defect', 'defect')] * 3 + [('defect', 'good')] + [('good', 'good')] * 6)
    first, second = paired_bootstrap(off, on), paired_bootstrap(off, on)
    assert first == second
    assert first['lift'] == 0.3
    assert first['lift_ci'][0] <= 0.3 <= first['lift_ci'][1]
    assert first['fixed_by_memory'] == 3 and first['broken_by_memory'] == 0


def test_an_offline_benchmark_runs_end_to_end_and_never_tests_on_teaching_photos():
    spec = importlib.util.spec_from_file_location('benchmark', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.main(['--dry-run'])
    groups = {r['case'] for r in result['rows']['memory_on']}
    teaching = {c['id'] for c in module.default_cases() if c['source_group'] in module.TEACH_GROUPS}
    assert not groups & teaching
    assert result['corrections'], 'the simulated model misses faint print, so teaching adds corrections'
    assert result['paired']['lift'] > 0
    assert module.main([]) is None, 'without --yes nothing runs'


def test_the_eval_route_reports_the_latest_run_without_per_case_rows(monkeypatch):
    from app import db
    from app import main
    result = {'id': 'bench-test', 'created_at': '2099-01-01T00:00:00+00:00', 'paired': {'lift': 0.1},
              'rows': {'memory_on': []}, 'notes': ['n']}
    with db.engine().begin() as c:
        c.execute(db.benchmark_runs.insert().values(id='bench-test', created_at=result['created_at'], payload=result))
    body = TestClient(main.app).get('/api/eval').json()
    assert body['benchmark']['id'] == 'bench-test'
    assert 'rows' not in body['benchmark']
