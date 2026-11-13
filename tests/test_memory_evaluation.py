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
