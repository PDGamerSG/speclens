"""Small live memory ablation on two held-aside synthetic source photos.

Runs 1 + 8 x repeats billable vision calls (nine for one pass), plus a SAM mask
for each claimed defect when SPECLENS_MASKS=1. The correction is taught once;
each repeat runs the four paired comparisons again. The labels come from
controlled image edits, not model judgments. Four cases from two source photos
are not four independent production observations, and repeats of the same
image measure how stable the model is, not new parts. Results are recorded
without requiring an improvement.

A run stops if the teaching correction is not recalled in a comparison. Such a
run is invalid: rerun it, and never drop a valid run because of its result.

The report records which script commit, server commit, prompt and models produced
it. A server in demo mode replays recorded results, so the script refuses it.
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def cases():
    """Keep teaching source 01 separate from every evaluation source."""
    result = []
    for index in (2, 3):
        original = Image.open(ROOT / f'fixtures/parts/hazelnut_gen_{index:02d}.jpg').convert('RGB')
        ink = Image.open(ROOT / f'fixtures/speclens/white-print-{index:02d}.png').convert('RGB')
        for expected in ('defect', 'good'):
            # A weaker print tests transfer; the untouched photo is a false-alarm control.
            image = Image.blend(original, ink, .30) if expected == 'defect' else original
            mask = np.any(np.array(image) != np.array(original), axis=2)
            out = io.BytesIO(); image.save(out, 'PNG')
            result.append({'id': f'source-{index:02d}-{expected}', 'source_group': f'generated-hazelnut-{index:02d}',
                           'expected_verdict': expected, 'changed_pixels': int(mask.sum()), 'data': out.getvalue()})
    return result


def git(*args) -> str:
    try:
        return subprocess.run(['git', *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ''


def summarize(rows):
    output = {}
    for arm in ('baseline', 'with_memory'):
        controls = [r for r in rows if r['expected_verdict'] == 'good']
        defects = [r for r in rows if r['expected_verdict'] == 'defect']
        output[arm] = {'correct': sum(r['comparison'][arm]['verdict'] == r['expected_verdict'] for r in rows),
                       'total': len(rows),
                       'false_alarms': sum(r['comparison'][arm]['verdict'] == 'defect' for r in controls),
                       'controls': len(controls),
                       'missed_defects': sum(r['comparison'][arm]['verdict'] != 'defect' for r in defects),
                       'defects': len(defects)}
    return output


def summarize_repeats(rows):
    """Per-pass summaries, their spread, and how often each case got the same verdict across passes."""
    passes = sorted({r.get('repeat', 1) for r in rows})
    per_pass = [summarize([r for r in rows if r.get('repeat', 1) == p]) for p in passes]
    out = {'passes': len(passes), 'per_pass': per_pass}
    for arm in ('baseline', 'with_memory'):
        correct = [s[arm]['correct'] for s in per_pass]
        out[arm] = {'correct_min': min(correct), 'correct_max': max(correct), 'correct_total': sum(correct),
                    'decisions_total': sum(s[arm]['total'] for s in per_pass),
                    'false_alarms_total': sum(s[arm]['false_alarms'] for s in per_pass),
                    'controls_total': sum(s[arm]['controls'] for s in per_pass),
                    'missed_defects_total': sum(s[arm]['missed_defects'] for s in per_pass),
                    'defects_total': sum(s[arm]['defects'] for s in per_pass)}
    # Share of passes that gave a case its most common verdict: 1.0 means every pass agreed.
    agreement = {}
    for case in sorted({r['id'] for r in rows}):
        agreement[case] = {}
        for arm in ('baseline', 'with_memory'):
            verdicts = [r['comparison'][arm]['verdict'] for r in rows if r['id'] == case]
            agreement[case][arm] = max(verdicts.count(v) for v in set(verdicts)) / len(verdicts)
    out['agreement'] = agreement
    return out


def positive(text):
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError('must be at least 1')
    return value


def main(argv=None, transport=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', default='http://localhost:8770')
    ap.add_argument('--out', type=Path, default=ROOT / 'var/evaluations')
    ap.add_argument('--repeats', type=positive, default=1, help='Passes over the four cases. The correction is taught once; each pass adds 8 vision calls.')
    args = ap.parse_args(argv)
    id = uuid.uuid4().hex[:10]
    scope = {'factory': f'SpecLens memory evaluation {id}', 'part_family': 'Whole hazelnut', 'spec_text': ''}
    report = {'id': id, 'created_at': datetime.now(timezone.utc).isoformat(), 'scope': scope, 'rows': [],
              'training_source_group': 'generated-hazelnut-01', 'test_source_groups': ['generated-hazelnut-02', 'generated-hazelnut-03'],
              'limits': (f"Four synthetic cases from two source photos, {'one pass' if args.repeats == 1 else f'{args.repeats} passes'}, "
                         'one part family. Paired calls are stochastic. This is a regression probe, not a production accuracy benchmark. '
                         'A run stops if the teaching correction is not recalled; such a run is invalid and is rerun, never dropped for its result.'),
              'provenance': {'script_commit': git('rev-parse', 'HEAD'), 'script_dirty': bool(git('status', '--porcelain')),
                             'base_url': args.base, 'repeats': args.repeats}}
    try:
        with httpx.Client(base_url=args.base.rstrip('/'), timeout=httpx.Timeout(240, connect=8), transport=transport) as client:
            health = client.get('/api/health')
            if not health.is_success:
                raise RuntimeError(f'HTTP {health.status_code} from /api/health. Check that the server is running.')
            health = health.json()
            report['provenance']['server'] = {k: health.get(k) for k in ('models', 'prompt_version', 'prompt_sha256', 'commit')}
            if health.get('demo_mode'):
                raise RuntimeError('The server is in demo mode, so results would be recorded replays. Set MODEL_API_KEY and HINDSIGHT_API_KEY.')
            def call(path, **kwargs):
                response = client.post('/api/workspace' + path, **kwargs)
                if not response.is_success:
                    raise RuntimeError(f'HTTP {response.status_code} from {path}. Check the app for connection details.')
                return response.json()
            print('Establishing a baseline on teaching source 01…', flush=True)
            first = call('/inspect', data={**scope, 'sample_id': 'white-print', 'memory_enabled': 'false'})
            correction = call('/corrections', json={'inspection_id': first['id'], 'verdict': 'defect', 'defect_type': 'print',
                'reviewer': 'Synthetic evaluation',
                'rule_text': 'Inspect faint white characters closely. Sharp printed characters, including low-contrast white ink, are print defects. Broad smooth highlights and natural shell stripes alone are acceptable.'})
            if correction['sync_status'] != 'synced':
                raise RuntimeError('The correction was not synced; no memory comparison was evaluated.')
            report.update({'teaching_inspection': first, 'correction': correction})
            evaluation_cases = cases()
            for repeat in range(1, args.repeats + 1):
                for item in evaluation_cases:
                    if item['source_group'] == report['training_source_group']:
                        raise RuntimeError('A teaching source entered the evaluation set.')
                    print(f"Pass {repeat}/{args.repeats}: comparing {item['id']} (label={item['expected_verdict']})…", flush=True)
                    comparison = call('/compare', data={**scope, 'expected_verdict': item['expected_verdict']},
                                      files={'file': (item['id'] + '.png', item['data'], 'image/png')})
                    if not any(f['source_id'] == correction['id'] for f in comparison['with_memory']['memories']):
                        raise RuntimeError('The teaching correction was not recalled; this is not a valid memory ablation.')
                    row = {k: v for k, v in item.items() if k != 'data'} | {'comparison': comparison}
                    report['rows'].append(row if args.repeats == 1 else row | {'repeat': repeat})
                    print(f"  off={comparison['baseline']['verdict']}, on={comparison['with_memory']['verdict']}", flush=True)
        report['summary'] = summarize(report['rows']) if args.repeats == 1 else summarize_repeats(report['rows'])
        report['passed'] = True
        print(json.dumps(report['summary'], indent=2), flush=True)
    except (httpx.HTTPError, RuntimeError, KeyError, ValueError) as exc:
        report['passed'] = False
        report['error'] = str(exc)
        print(f'Evaluation stopped: {exc}', file=sys.stderr, flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f'memory-{id}.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Report: {path}', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
