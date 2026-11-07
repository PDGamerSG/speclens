"""Small live memory ablation on two held-aside synthetic source photos.

Runs nine billable vision calls. The labels come from controlled image edits,
not model judgments. Four cases from two source photos are not four independent
production observations. Results are recorded without requiring an improvement.
"""
from __future__ import annotations

import argparse
import io
import json
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


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base', default='http://localhost:8770')
    ap.add_argument('--out', type=Path, default=ROOT / 'var/evaluations')
    args = ap.parse_args()
    id = uuid.uuid4().hex[:10]
    scope = {'factory': f'Chief Skill memory evaluation {id}', 'part_family': 'Whole hazelnut', 'spec_text': ''}
    report = {'id': id, 'created_at': datetime.now(timezone.utc).isoformat(), 'scope': scope, 'rows': [],
              'training_source_group': 'generated-hazelnut-01', 'test_source_groups': ['generated-hazelnut-02', 'generated-hazelnut-03'],
              'limits': 'Four synthetic cases from two source photos, one pass, one part family. Paired calls are stochastic. This is a regression probe, not a production accuracy benchmark.'}
    try:
        with httpx.Client(base_url=args.base.rstrip('/'), timeout=httpx.Timeout(240, connect=8)) as client:
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
            for item in cases():
                if item['source_group'] == report['training_source_group']:
                    raise RuntimeError('A teaching source entered the evaluation set.')
                print(f"Comparing {item['id']} (label={item['expected_verdict']})…", flush=True)
                comparison = call('/compare', data={**scope, 'expected_verdict': item['expected_verdict']},
                                  files={'file': (item['id'] + '.png', item['data'], 'image/png')})
                if not any(f['source_id'] == correction['id'] for f in comparison['with_memory']['memories']):
                    raise RuntimeError('The teaching correction was not recalled; this is not a valid memory ablation.')
                report['rows'].append({k: v for k, v in item.items() if k != 'data'} | {'comparison': comparison})
                print(f"  off={comparison['baseline']['verdict']}, on={comparison['with_memory']['verdict']}", flush=True)
        report['summary'] = summarize(report['rows'])
        report['passed'] = True
        print(json.dumps(report['summary'], indent=2), flush=True)
    except (httpx.HTTPError, RuntimeError, KeyError) as exc:
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
