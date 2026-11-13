"""The live ablation must keep teaching images out and count false alarms honestly."""
import importlib.util
from pathlib import Path


def evaluation():
    path = Path(__file__).resolve().parents[1] / 'scripts/evaluate_memory.py'
    spec = importlib.util.spec_from_file_location('speclens_memory_evaluation', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_evaluation_cases_use_new_sources_and_unedited_controls():
    rows = evaluation().cases()
    assert len(rows) == 4
    assert {r['source_group'] for r in rows} == {'generated-hazelnut-02', 'generated-hazelnut-03'}
    assert all(r['changed_pixels'] > 0 for r in rows if r['expected_verdict'] == 'defect')
    assert all(r['changed_pixels'] == 0 for r in rows if r['expected_verdict'] == 'good')


def test_summary_counts_false_alarms_as_a_regression_even_when_detection_improves():
    rows = [
        {'expected_verdict': 'defect', 'comparison': {'baseline': {'verdict': 'good'}, 'with_memory': {'verdict': 'defect'}}},
        {'expected_verdict': 'good', 'comparison': {'baseline': {'verdict': 'good'}, 'with_memory': {'verdict': 'defect'}}},
    ]
    summary = evaluation().summarize(rows)
    assert summary['baseline']['missed_defects'] == 1
    assert summary['with_memory']['missed_defects'] == 0
    assert summary['with_memory']['false_alarms'] == 1
    assert summary['baseline']['correct'] == summary['with_memory']['correct'] == 1


def fake_server(demo_mode=False):
    """A SpecLens server that answers the evaluation's calls without a model. Records each request path."""
    import httpx
    paths = []
    def respond(request):
        paths.append((request.method, request.url.path))
        if request.url.path == '/api/health':
            return httpx.Response(200, json={'ok': True, 'demo_mode': demo_mode, 'models': ['muse-spark-1.3'],
                                             'prompt_version': 'inspector-test', 'prompt_sha256': '0123456789abcdef',
                                             'commit': 'server-commit'})
        if request.url.path.endswith('/inspect'):
            return httpx.Response(200, json={'id': 'insp-teach', 'verdict': 'good'})
        if request.url.path.endswith('/corrections'):
            return httpx.Response(200, json={'id': 'correction-teach', 'sync_status': 'synced'})
        return httpx.Response(200, json={'baseline': {'verdict': 'good', 'memories': []},
                                         'with_memory': {'verdict': 'defect', 'memories': [{'source_id': 'correction-teach'}]}})
    return httpx.MockTransport(respond), paths


def read_report(out):
    import json
    [path] = out.glob('memory-*.json')
    return json.loads(path.read_text())


def test_a_demo_mode_server_cannot_produce_evidence(tmp_path):
    module = evaluation()
    transport, paths = fake_server(demo_mode=True)
    assert module.main(['--base', 'http://speclens.test', '--out', str(tmp_path)], transport=transport) == 1
    report = read_report(tmp_path)
    assert report['passed'] is False
    assert 'demo mode' in report['error']
    assert paths == [('GET', '/api/health')]


def test_the_report_records_which_code_prompt_and_models_produced_it(tmp_path):
    module = evaluation()
    module.git = lambda *args: 'script-commit' if args[0] == 'rev-parse' else ' M scripts/evaluate_memory.py'
    transport, _ = fake_server()
    assert module.main(['--base', 'http://speclens.test', '--out', str(tmp_path)], transport=transport) == 0
    provenance = read_report(tmp_path)['provenance']
    assert provenance['script_commit'] == 'script-commit'
    assert provenance['script_dirty'] is True
    assert provenance['base_url'] == 'http://speclens.test'
    assert provenance['server'] == {'models': ['muse-spark-1.3'], 'prompt_version': 'inspector-test',
                                    'prompt_sha256': '0123456789abcdef', 'commit': 'server-commit'}


def row(case, repeat, baseline, with_memory, expected='defect'):
    return {'id': case, 'repeat': repeat, 'expected_verdict': expected,
            'comparison': {'baseline': {'verdict': baseline}, 'with_memory': {'verdict': with_memory}}}


def test_repeated_passes_report_their_spread_and_totals():
    rows = [row('a', 1, 'good', 'defect'), row('b', 1, 'good', 'good', 'good'),
            row('a', 2, 'defect', 'defect'), row('b', 2, 'good', 'defect', 'good')]
    summary = evaluation().summarize_repeats(rows)
    assert summary['passes'] == 2 and len(summary['per_pass']) == 2
    assert summary['baseline'] == {'correct_min': 1, 'correct_max': 2, 'correct_total': 3, 'decisions_total': 4,
                                    'false_alarms_total': 0, 'controls_total': 2,
                                    'missed_defects_total': 1, 'defects_total': 2}
    assert (summary['with_memory']['correct_min'], summary['with_memory']['correct_max']) == (1, 2)
    assert summary['with_memory']['false_alarms_total'] == 1


def test_agreement_shows_how_often_a_case_got_the_same_verdict():
    rows = [row('a', 1, 'good', 'defect'), row('a', 2, 'defect', 'defect')]
    assert evaluation().summarize_repeats(rows)['agreement'] == {'a': {'baseline': 0.5, 'with_memory': 1.0}}


def test_one_pass_keeps_the_published_report_shape(tmp_path):
    transport, _ = fake_server()
    assert evaluation().main(['--base', 'http://speclens.test', '--out', str(tmp_path)], transport=transport) == 0
    report = read_report(tmp_path)
    assert len(report['rows']) == 4
    assert all('repeat' not in r for r in report['rows'])
    assert set(report['summary']) == {'baseline', 'with_memory'}
    assert report['summary']['with_memory']['total'] == 4
    assert report['provenance']['repeats'] == 1


def test_repeats_teach_once_and_rerun_every_comparison(tmp_path):
    transport, paths = fake_server()
    assert evaluation().main(['--base', 'http://speclens.test', '--out', str(tmp_path), '--repeats', '2'],
                             transport=transport) == 0
    report = read_report(tmp_path)
    assert [p for _, p in paths].count('/api/workspace/corrections') == 1
    assert [p for _, p in paths].count('/api/workspace/compare') == 8
    assert sorted({r['repeat'] for r in report['rows']}) == [1, 2]
    assert report['summary']['passes'] == 2
    assert report['summary']['with_memory']['decisions_total'] == 8
    assert '2 passes' in report['limits']
