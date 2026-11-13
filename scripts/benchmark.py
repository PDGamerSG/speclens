"""Benchmark SpecLens with memory off and on, on labelled photos split by source photo.

    .venv/bin/python scripts/benchmark.py              # prints the plan and the cost estimate, runs nothing
    .venv/bin/python scripts/benchmark.py --yes        # billable: Model API and Hindsight calls
    .venv/bin/python scripts/benchmark.py --dry-run    # offline, with a simulated model and memory

Protocol
1. Cases from teaching sources are inspected with memory off. Each wrong decision gets one correction written
   from the case's label, as an engineer would.
2. Held-out cases, from other source photos, are inspected twice: memory off, then memory on.
3. Precision, recall, F1, the confusion matrix and accuracy with a paired bootstrap 95% interval are reported.

Labels come from the fixtures' provenance (controlled image edits), not from a model. Cases that share a source
photo are not independent observations, which is why the split is by source photo. The default set is small;
add labelled photos with --manifest to tighten the intervals.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from PIL import Image  # noqa: E402

COST_PER_CALL = 0.0035
MASK_COST = 0.0025
TEACH_GROUPS = ('hazelnut-01', 'hazelnut-03')
RULES = {
    'print': 'Sharp white or dark characters, dots or lines on the shell are ink print, even when faint. Reject them under clause 4.4.',
    'hole': 'A small dark round pit with a torn rim is a hole through the shell. Reject it under clause 4.1, whatever its size.',
    'crack': 'A thin dark line or split running across the shell is a crack. Reject it under clause 4.2.',
    'cut': 'A short straight-edged notch showing paler material is a cut. Reject it under clause 4.3.',
    'good': 'Natural stripes, gloss, small specks and the fuzzy cap are normal shell texture. Accept the part under clause 3.',
}


def default_cases() -> list[dict]:
    """Labelled fixtures: untouched generated parts, controlled ink edits and accepted forge composites."""
    cases = [{'id': f'good-{i:02d}', 'path': f'parts/hazelnut_gen_{i:02d}.jpg', 'expected_verdict': 'good',
              'defect_type': 'good', 'source_group': f'hazelnut-{i:02d}'} for i in range(1, 6)]
    for item in json.loads((ROOT / 'fixtures/speclens/manifest.json').read_text()):
        group = item['source'].split('_gen_')[1][:2]
        cases.append({'id': item['id'], 'path': item['image'], 'expected_verdict': 'defect',
                      'defect_type': item['defect_type'], 'source_group': f'hazelnut-{group}'})
    run = json.loads((ROOT / 'fixtures/demo_run/run.json').read_text())
    for sample in run['samples']:
        path = f'demo_run/samples/{sample["id"]}_composite.jpg'
        if sample['status'] == 'accepted' and (ROOT / 'fixtures' / path).exists():
            group = sample['part_id'].split('_gen_')[1][:2]
            cases.append({'id': sample['id'], 'path': path, 'expected_verdict': 'defect',
                          'defect_type': sample['defect_type'], 'source_group': f'hazelnut-{group}'})
    return cases


def load_cases(manifest: Path | None) -> list[dict]:
    if manifest is None:
        return default_cases()
    base = manifest.parent
    cases = json.loads(manifest.read_text())
    for case in cases:
        case['path'] = str((base / case['path']).resolve())
    return cases


def read(case: dict) -> bytes:
    path = Path(case['path'])
    return (path if path.is_absolute() else ROOT / 'fixtures' / path).read_bytes()


def simulated_service(cases: list[dict], var: Path):
    """An offline service: the model misses faint print until a print standard is recalled."""
    import httpx

    from app.workspace.memory import HindsightMemory
    from app.workspace.service import WorkspaceService
    from app.workspace.store import Store

    labels = {}
    for case in cases:
        with Image.open(io.BytesIO(read(case))) as image:
            image = image.convert('RGB')
            image.thumbnail((1280, 1280))
            labels[image.tobytes()[:4096]] = case
    facts: dict[str, dict] = {}

    def respond(request):
        if request.url.path.endswith('/memories'):
            item = json.loads(request.content)['items'][0]
            facts[item['document_id']] = {'id': 'f-' + item['document_id'], 'text': item['content'][-200:],
                                          'document_id': item['document_id']}
            return httpx.Response(200, json={'success': True, 'items_count': 1})
        return httpx.Response(200, json={'results': list(facts.values())})

    def inspector(img, spec, types, **kw):
        case = labels.get(img.tobytes()[:4096], {'expected_verdict': 'good', 'defect_type': 'good'})
        defect = case['expected_verdict'] == 'defect'
        if defect and case['defect_type'] == 'print' and not kw.get('memory_context'):
            defect = False  # the simulated model mistakes ink for gloss
        return {'verdict': 'defect' if defect else 'good', 'defect': defect, 'type': case['defect_type'] if defect else 'good',
                'confidence': .8, 'rationale': 'Simulated.', 'box_px': [10, 10, 60, 60] if defect else None,
                'mask': None, 'ms': 1, 'cost_usd': 0.0}

    memory = HindsightMemory('https://memory.simulated', 'offline', transport=httpx.MockTransport(respond))
    return WorkspaceService(Store(var / 'benchmark.sqlite3'), memory, inspector=inspector, media_root=var / 'media')


def run(service, cases: list[dict], teach_groups: tuple[str, ...], log=print) -> dict:
    from app.bench import binary_metrics, paired_bootstrap
    from app.forge.spec import DEFAULT_SPEC
    from app.workspace.store import Scope

    run_id = f'bench-{uuid.uuid4().hex[:10]}'
    scope = Scope(f'Benchmark {run_id}', 'Whole hazelnut', DEFAULT_SPEC, owner_id='benchmark')
    teach = [c for c in cases if c['source_group'] in teach_groups]
    test = [c for c in cases if c['source_group'] not in teach_groups]
    if not test or not teach:
        raise SystemExit('Both the teaching and the held-out split need cases. Check --teach-groups.')
    started = time.time()

    def inspect(case, use_memory):
        result = service.run(read(case), Path(case['path']).name, scope, use_memory=use_memory,
                             source_kind='benchmark', source_group=case['source_group'], sample_id=case['id'])
        return {'case': case['id'], 'expected': case['expected_verdict'], 'expected_type': case['defect_type'],
                'verdict': result['verdict'], 'type': result['type'], 'confidence': result['confidence'],
                'cost_usd': result.get('cost_usd', 0), 'ms': result.get('ms', 0), 'inspection_id': result['id'],
                'cited': [m['source_id'] for m in result.get('memories', [])]}

    log(f'{run_id}: {len(teach)} teaching cases, {len(test)} held-out cases')
    baseline = [inspect(c, False) for c in test]
    corrections = []
    for case in teach:
        row = inspect(case, False)
        if (row['verdict'] in ('defect', 'uncertain')) != (case['expected_verdict'] == 'defect'):
            saved = service.correct(row['inspection_id'], verdict=case['expected_verdict'],
                                    defect_type=case['defect_type'] if case['expected_verdict'] == 'defect' else 'good',
                                    rule_text=case.get('rule') or RULES.get(case['defect_type'], RULES['good']),
                                    reviewer='Benchmark labels')
            corrections.append({'case': case['id'], 'correction_id': saved['id'], 'sync_status': saved['sync_status']})
    log(f'{len(corrections)} corrections taught')
    memory = [inspect(c, True) for c in test]
    return {'id': run_id, 'created_at': datetime.now(timezone.utc).isoformat(), 'duration_s': round(time.time() - started, 1),
            'protocol': 'Teach on some source photos, test on held-out source photos, memory off then on.',
            'teach_groups': list(teach_groups), 'teach_cases': len(teach), 'test_cases': len(test),
            'corrections': corrections,
            'memory_off': binary_metrics(baseline), 'memory_on': binary_metrics(memory),
            'paired': paired_bootstrap(baseline, memory),
            'cost_usd': round(sum(r['cost_usd'] for r in baseline + memory), 4),
            'rows': {'memory_off': baseline, 'memory_on': memory},
            'notes': ['Labels come from controlled image edits on generated photos, not from production parts.',
                      'Cases that share a source photo are not independent; the split is by source photo.']}


def save(result: dict, dry_run: bool) -> Path:
    from app import db
    from app.config import RESULTS, VAR
    if dry_run:
        target = VAR / 'benchmarks' / f'{result["id"]}.json'
    else:
        target = RESULTS / 'eval.json'
        with db.engine().begin() as c:
            c.execute(db.benchmark_runs.insert().values(id=result['id'], created_at=result['created_at'], payload=result))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2))
    return target


def main(argv: list[str] | None = None) -> dict | None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--manifest', type=Path, help='JSON list of {id, path, expected_verdict, defect_type, source_group}')
    parser.add_argument('--teach-groups', default=','.join(TEACH_GROUPS))
    parser.add_argument('--yes', action='store_true', help='run the billable benchmark')
    parser.add_argument('--dry-run', action='store_true', help='run offline with a simulated model and memory')
    args = parser.parse_args(argv)
    cases = load_cases(args.manifest)
    teach_groups = tuple(g.strip() for g in args.teach_groups.split(',') if g.strip())
    teach = sum(c['source_group'] in teach_groups for c in cases)
    test = len(cases) - teach
    calls = teach + 2 * test
    estimate = calls * COST_PER_CALL + sum(c['expected_verdict'] == 'defect' for c in cases) * 2 * MASK_COST
    print(f'{len(cases)} cases: {teach} teaching, {test} held out. {calls} vision calls, about ${estimate:.2f} '
          'with masks, plus Hindsight usage.')
    if args.dry_run:
        from app.config import VAR
        result = run(simulated_service(cases, VAR / 'benchmarks'), cases, teach_groups)
    elif args.yes:
        from app.config import API_KEY
        from app.workspace.routes import service
        if not API_KEY or not service.memory.configured:
            raise SystemExit('Set MODEL_API_KEY and connect Hindsight before a live benchmark.')
        result = run(service, cases, teach_groups)
    else:
        print('Nothing was run. Add --yes to run it, or --dry-run to check the pipeline offline.')
        return None
    path = save(result, args.dry_run)
    paired = result['paired']
    print(f'Accuracy memory off {paired["accuracy_off"]:.2f} {paired["accuracy_off_ci"]}, '
          f'memory on {paired["accuracy_on"]:.2f} {paired["accuracy_on_ci"]}, lift {paired["lift"]:+.2f} {paired["lift_ci"]}')
    print(f'Saved to {path}')
    return result


if __name__ == '__main__':
    main()
