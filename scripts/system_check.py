"""Check the live SpecLens workflow; records observations, never assumes model improvement.

Run with the configured backend running. Makes four billable vision calls and
Hindsight retain/recall/reflect calls in a separate, uniquely named workspace.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='http://localhost:8770')
    parser.add_argument('--out', type=Path, default=ROOT / 'var' / 'checks')
    args = parser.parse_args()
    identity = uuid.uuid4().hex[:10]
    scope = {'factory': f'SpecLens connection check {identity}', 'part_family': 'Whole hazelnut', 'spec_text': ''}
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'base': args.base,
              'scope': scope, 'requested_check': 'live service integration', 'steps': {},
              'note': 'Integration observations only. No accuracy or learning improvement is assumed.'}

    def check(name: str, condition: bool):
        if not condition:
            raise RuntimeError(name)
        print(f'[PASS] {name}', flush=True)

    try:
        with httpx.Client(base_url=args.base.rstrip('/'), timeout=httpx.Timeout(240, connect=8)) as client:
            def request(method: str, path: str, **kwargs):
                response = client.request(method, '/api/workspace' + path, **kwargs)
                if not response.is_success:
                    try:
                        detail = response.json().get('detail', '')
                    except (ValueError, AttributeError):
                        detail = ''
                    raise RuntimeError(f'HTTP {response.status_code} at {path}: {str(detail)[:300]}')
                return response.json()

            status = request('GET', '/status')
            report['steps']['status'] = status
            check('Vision key and Hindsight endpoint are configured', status['model_configured'] and status['memory_configured'])
            print('Inspecting the first sample with memory off…', flush=True)
            first = request('POST', '/inspect', data={**scope, 'sample_id': 'white-print', 'memory_enabled': 'false'})
            report['steps']['baseline'] = first
            check('Baseline inspection returned without recalled memory', first['memory_status'] == 'disabled' and not first['memories'])

            print('Retaining a quality engineer standard…', flush=True)
            correction = request('POST', '/corrections', json={
                'inspection_id': first['id'], 'verdict': 'defect', 'defect_type': 'print',
                'reviewer': 'Connection check',
                'rule_text': 'Sharp white printed characters on the shell are ink. Reject them as print defects; broad, smooth natural highlights alone remain acceptable.'})
            report['steps']['correction'] = correction
            check('Hindsight confirmed retain', correction['sync_status'] == 'synced')

            recalled = request('POST', '/recall', json=scope)
            report['steps']['recall'] = recalled
            check('Recall cites the retained correction', any(f['source_id'] == correction['id'] for f in recalled['memories']))

            print('Inspecting a different sample with recalled memory…', flush=True)
            next_part = request('POST', '/inspect', data={**scope, 'sample_id': 'second-print', 'memory_enabled': 'true'})
            report['steps']['next_inspection'] = next_part
            check('The next inspection applied a cited correction', any(f['source_id'] == correction['id'] for f in next_part['memories']))
            check('The next sample differs from the correction image', next_part['image_sha256'] != first['image_sha256'])

            reflected = request('POST', '/reflect', json=scope)
            report['steps']['reflection'] = reflected
            check('Hindsight returned a standards reflection', bool(reflected.get('summary', '').strip()))

            print('Running the paired memory comparison…', flush=True)
            pair = request('POST', '/compare', data={**scope, 'sample_id': 'second-print', 'expected_verdict': 'defect'})
            report['steps']['comparison'] = pair
            a, b = pair['baseline'], pair['with_memory']
            check('Comparison fixes image, model, and base specification',
                  a['image_sha256'] == b['image_sha256'] and a['spec_text'] == b['spec_text'] and a['model'] == b['model'])
            print(f"Observed decisions: memory off={a['verdict']}; memory on={b['verdict']}. No gain is assumed.", flush=True)

            overview = request('GET', '/overview', params=scope)
            check('The durable workspace includes its correction and four inspections',
                  overview['stats']['inspections'] == 4 and any(c['id'] == correction['id'] for c in overview['corrections']))
            report['steps']['overview_stats'] = overview['stats']
        report['passed'] = True
    except (httpx.HTTPError, RuntimeError, KeyError) as exc:
        report['passed'] = False
        report['error'] = str(exc)
        print(f'[FAIL] {exc}', file=sys.stderr, flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f'connection-{identity}.json'
    path.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Report: {path}', flush=True)
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
