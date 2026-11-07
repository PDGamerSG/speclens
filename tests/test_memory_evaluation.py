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
