"""Additive operator seed for the explicitly named, public demo team only.

No account provisioning, model inference or quality-memory calls. Stable IDs
make a second run a no-op for existing records, including edits made by visitors.
"""
from __future__ import annotations

import hashlib
import io
import random
import re
from datetime import datetime, timedelta, timezone

from PIL import Image
import sqlalchemy as sa

from .. import db
from ..workspace.store import Scope
from . import tables
from .demo_images import sample_image
from .integration import complete_capture, optional, propose_standard, reserve_capture
from .resolution import lot_resolution
from .store import PilotStore, now
from .validation import ValidationImport, evaluate_validation

SEED = 'factory-demo-v1'
TIMELINE = 'four-weeks-v1'
SPAN_DAYS = 27
PREFIX = 'demo-v1-'
DEMO_TEAM = 'SpecLens Demo Factory'
COUNTS = {'product': 6, 'revision': 18, 'station': 12, 'lot': 18, 'capture': 186,
          'review': 186, 'standard': 24, 'nonconformance': 18, 'validation': 4}

# Recipes are examples for exploring the workflow, not validated acceptance criteria.
PRODUCTS = [
    dict(key='hazelnut', code='DEMO-HZ02', name='Whole hazelnut', area='Food intake',
         description='Incoming shell inspection, natural texture and foreign markings.',
         defects=[('print', 'Foreign print', 'Reject ink, paint or printed characters on the shell.'),
                  ('crack', 'Open shell crack', 'Reject an open crack exposing the kernel.'),
                  ('hole', 'Shell hole', 'Reject visible insect holes or punctures.')],
         setup='One dry shell on the marked tray; top-down camera and diffuse side lighting.',
         cause='Transfer from a marked intake tray', action='Replace the marked tray and inspect the segregated sample.'),
    dict(key='seal', code='DEMO-PK01', name='Snack blister pack', area='Packaging line',
         description='Seal continuity, trapped debris and pack integrity before dispatch.',
         defects=[('seal_gap', 'Seal discontinuity', 'Reject a visible break in the seal perimeter.'),
                  ('contamination', 'Seal contamination', 'Reject debris crossing the seal band.'),
                  ('puncture', 'Film puncture', 'Reject any visible puncture in the top film.')],
         setup='Flat pack, full seal perimeter visible; diffuse light plus an oblique verification view.',
         cause='Illustrative sealing-jaw residue', action='Clean the jaw, verify the setup and review the held packs.'),
    dict(key='cap', code='DEMO-CP01', name='Moulded closure cap', area='Moulding cell',
         description='Rim integrity, flash and surface contamination on a blue polymer closure.',
         defects=[('crack', 'Rim crack', 'Reject a split crossing the cap rim.'),
                  ('flash', 'Moulding flash', 'Reject loose flash on the sealing face.'),
                  ('contamination', 'Foreign inclusion', 'Reject a visible foreign inclusion in the closure.')],
         setup='Cap face up in the nest; fixed focus and a ring light; keep the full rim in frame.',
         cause='Illustrative tool wear at the rim cavity', action='Inspect the tool insert and verify a fresh setup sample.'),
    dict(key='washer', code='DEMO-MW01', name='Aluminium spacer washer', area='Machining cell',
         description='Face damage and edge condition; dimensions require separate calibrated gauges.',
         defects=[('scratch', 'Face scratch', 'Flag visible face scoring for engineer review.'),
                  ('burr', 'Raised burr', 'Reject a loose or raised burr on either edge.'),
                  ('corrosion', 'Surface corrosion', 'Reject visible corrosion or embedded contamination.')],
         setup='Washer flat on a matte tray; grazing light for burrs; no image-based dimension release.',
         cause='Illustrative contact damage in the transfer bin', action='Line the transfer bin and review the deburring setup.'),
    dict(key='label', code='DEMO-LB01', name='Printed carton label', area='Print verification',
         description='Print legibility, registration and label surface condition.',
         defects=[('misprint', 'Missing print', 'Reject missing or broken mandatory text.'),
                  ('smudge', 'Print smudge', 'Reject smearing that obscures required characters.'),
                  ('cut', 'Label tear', 'Reject a tear crossing printed information.')],
         setup='Label flat and square to camera; glare-free light; barcode decoding is a separate check.',
         cause='Illustrative print-head contamination', action='Clean the print head and check the next setup strip.'),
    dict(key='pcb', code='DEMO-PC01', name='Sensor board assembly', area='Electronics bench',
         description='Visible component presence and solder condition; electrical testing remains separate.',
         defects=[('missing_component', 'Missing component', 'Reject an unpopulated required component position.'),
                  ('solder_bridge', 'Solder bridge', 'Reject a visible bridge between isolated pads.'),
                  ('contamination', 'Board contamination', 'Flag foreign residue for engineer review.')],
         setup='Board component-side up in an ESD nest; fixed orientation and diffuse ring light.',
         cause='Illustrative feeder-position error', action='Verify feeder setup, segregate the tray and inspect replacement samples.'),
]


def _identity(store, team_id):
    query = sa.select(tables.users.c.id, tables.users.c.username, tables.users.c.name,
                      tables.memberships.c.role).select_from(tables.users.join(tables.memberships).join(
                          tables.teams, tables.memberships.c.team_id == tables.teams.c.id)).where(
        tables.teams.c.id == team_id, tables.teams.c.name == DEMO_TEAM,
        tables.users.c.username == 'demo.speclens', tables.memberships.c.active.is_(True),
        tables.memberships.c.role == 'engineer')
    with store.engine.connect() as c:
        actor = c.execute(query).mappings().first()
    if actor is None:
        raise ValueError('Refusing to seed: target must be the public demo team with its active demo engineer.')
    return dict(actor)


def _ensure(pilot, team, actor, kind, id, fields):
    existing = optional(pilot, team, id, kind)
    if existing is not None:
        if existing.get('demo_seed') != SEED:
            raise ValueError('Refusing to overwrite a record outside this demo seed.')
        return existing, False
    return pilot.create(team, kind, {**fields, 'demo_seed': SEED}, actor=actor, id=id), True


def _capture(store, media, pilot, team, actor, product, recipe, revision, station, lot, number, *, retake=None):
    suffix = f'{recipe["key"]}-{lot["reference"].rsplit("-", 1)[-1]}-{number:03d}'
    capture_id = f'{PREFIX}capture-{suffix}' + ('-retake' if retake else '')
    inspection_id = 'insp-' + hashlib.sha256(f'{team}:{capture_id}'.encode()).hexdigest()[:24]
    existing = store.inspection(inspection_id)
    if existing is not None:
        if existing.get('owner_id') != team or existing.get('demo_seed') != SEED:
            raise ValueError('Conflicting demo inspection identity.')
        # A disconnect can happen after the inspection commit but before its
        # capture/review commit. Repair those links without replacing decisions.
        complete_capture(store, existing)
        review = pilot.get(team, 'review-' + inspection_id.removeprefix('insp-'), 'review')
        unfinished = review['version'] == 1 and not review.get('history')
        return existing, unfinished
    part = f'DEMO-{recipe["key"].upper()}-{lot["reference"].rsplit("-", 1)[-1]}-P{number:03d}'
    defect = recipe['defects'][(number - 2) % 3][0] if number in (2, 3, 4, 6, 8, 9) and not retake else None
    verdict = 'uncertain' if number in (4, 6, 9) and not retake else 'defect' if defect else 'good'
    data, box = sample_image(recipe['key'], recipe['name'], part + (' / retake' if retake else ''), defect)
    context = pilot.capture_context(team, actor, revision_id=revision['id'], station_id=station['id'],
        lot_id=lot['id'], physical_part_id=part, capture_id=capture_id, retake_of=retake)
    context['demo_seed'] = SEED
    scope = Scope(product['factory'], product['name'], revision['spec_text'], team, revision_id=revision['id'])
    id, saved, context = reserve_capture(store, scope, context, data, memory=False)
    if saved is not None:
        return saved, False
    media.put(f'{id}.jpg', data, 'image/jpeg')
    with Image.open(io.BytesIO(data)) as image:
        image_hash = hashlib.sha256(f'RGB:{image.width}x{image.height}:'.encode() + image.convert('RGB').tobytes()).hexdigest()
    finding = f'Illustrated {defect.replace("_", " ")}; compare with the linked sample clause.' if defect else 'Illustrated nominal appearance.'
    inspection = store.add_inspection({
        'id': id, 'scope_id': scope.id, 'owner_id': team, 'factory': scope.factory, 'part_family': scope.part_family,
        'spec_text': scope.spec_text, 'verdict': verdict, 'defect': verdict == 'defect', 'type': defect or 'good',
        'confidence': 0, 'rationale': f'Synthetic demonstration: {finding} No model was run; this outcome was staged.',
        'box_px': box, 'image_url': f'/files/workspace/{id}.jpg', 'image_width': 800, 'image_height': 560,
        'image_sha256': image_hash, 'filename': f'{part}.jpg', 'source_kind': 'synthetic_sample',
        'source_group': SEED, 'sample_id': capture_id, 'demo_seed': SEED, 'activity_kind': 'inspection',
        'memory_enabled': False, 'memory_status': 'disabled', 'memories': [], 'reference_crops': [],
        'ms': 0, 'cost_usd': 0, 'model': 'Illustrative sample / no inference',
        'pilot': {**context, 'owner_id': team, 'quarantined': False,
                  'model_configuration': {'synthetic': True, 'inference_executed': False}},
    })
    complete_capture(store, inspection)
    return inspection, True


def _disposition(pilot, team, actor, inspection, number, closed_lot, *, replacement=False):
    review_id = 'review-' + inspection['id'].removeprefix('insp-')
    review = pilot.get(team, review_id, 'review')
    outcome = ('retake' if number == 6 else 'reject' if inspection['type'] != 'good' else 'accept')
    status = 'closed'
    if replacement:
        outcome = 'accept'
    elif not closed_lot:
        status = 'open' if number in (4, 10) else 'claimed' if number == 8 else 'closed'
        outcome = 'hold' if number == 9 else outcome
    reason = {
        'accept': 'Demo decision: nominal appearance accepted against the illustrated recipe.',
        'reject': 'Demo decision: illustrated finding rejected against the linked clause.',
        'retake': 'Demo decision: request another view before releasing this physical part.',
        'hold': 'Demo decision: keep this part on hold while the illustrated issue is investigated.',
    }[outcome] if status == 'closed' else ''
    timestamp = now()
    changes = {'status': status, 'outcome': outcome if status == 'closed' else None, 'reason': reason,
        'history': [{'status': status, 'outcome': outcome if status == 'closed' else None,
                     'reason': reason, 'actor': actor, 'at': timestamp}],
        'assignee': actor if status == 'claimed' else None,
        'reviewer': actor if status == 'closed' else None, 'closed_at': timestamp if status == 'closed' else None}
    pilot.update(team, review_id, review['version'], changes, actor)


def _standard(store, pilot, team, actor, inspection, index, recipe):
    correction = store.correction_for_inspection(inspection['id'])
    defect = inspection['type']
    rule = next((item[2] for item in recipe['defects'] if item[0] == defect),
                'Accept the illustrated nominal appearance when all required views are present.')
    if correction is None:
        correction = store.add_correction(inspection['id'],
            id='correction-' + inspection['id'].removeprefix('insp-'), verdict='good' if defect == 'good' else 'defect',
            defect_type=defect, rule_text=f'Demo example: {rule}', reviewer=actor['name'], actor=actor)
    elif correction.get('id') != 'correction-' + inspection['id'].removeprefix('insp-'):
        return  # A visitor's later proposal is never replaced.
    standard = propose_standard(store, inspection, correction)
    status = ('approved', 'approved', 'candidate', 'retired')[index]
    if status != 'candidate' and standard['version'] == 1 and standard.get('status') == 'candidate':
        pilot.update(team, standard['id'], standard['version'], {
            'status': status, 'reason': 'Illustrative lifecycle state, seeded without a live approval or memory sync.'}, actor)


def _issue(pilot, team, actor, recipe, lot, inspection, stage):
    issue, created = _ensure(pilot, team, actor, 'nonconformance', lot['id'].replace('lot-', 'issue-'), {
        'title': f'Demo: {recipe["defects"][0][1]} / {lot["reference"]}', 'lot_id': lot['id'],
        'inspection_id': inspection['id'], 'severity': ('minor', 'major', 'critical')[stage - 1],
        'description': f'Synthetic scenario: {recipe["defects"][0][2]} Explore containment and corrective action using this example.',
        'requirement': 'Illustrative specification clause 1. No real factory release decision is implied.',
        'containment': 'Demo: segregate the affected tray and label the matching physical parts.',
        'root_cause': f'Demo hypothesis: {recipe["cause"].lower()}.',
        'evidence': f'Illustrated source {inspection["filename"]}; staged evidence only.',
        'assignee': actor['id'], 'created_by': actor, 'history': [], 'status': 'open',
    })
    if (created or issue['version'] == 1) and stage != 3:
        status = 'closed' if stage == 1 else 'contained'
        changes = {'status': status, 'history': [{'status': status, 'actor': actor, 'at': now(),
                                                'changes': {'status': status, 'synthetic': True}}]}
        if status == 'closed':
            changes.update(corrective_action=f'Demo action: {recipe["action"]}',
                resolution='Demo closure: the replacement sample is reviewed and the illustrative issue is resolved.',
                closed_by=actor, closed_at=now())
        pilot.update(team, issue['id'], issue['version'], changes, actor)


def _validation(index):
    rng = random.Random(7300 + index)
    cases = []
    for cluster in range(12):
        for part in range(20):
            truth = 'defect' if part % 3 == 0 else 'good'
            opposite = 'good' if truth == 'defect' else 'defect'
            def output(error, review, mistake):
                value = rng.random()
                return 'error' if value < error else 'uncertain' if value < error + review else opposite if value < error + review + mistake else truth
            case = dict(sample_id=f'DEMO-V{index}-{cluster}-{part}',
                physical_part_id=f'DEMO-V{index}-P{cluster}-{part}', lot_id=f'DEMO-V{index}-LOT-{cluster}',
                session_id=f'DEMO-V{index}-SESSION-{cluster}', truth=truth,
                severity=('minor', 'major', 'critical')[cluster % 3] if truth == 'defect' else None,
                baseline=output(.02, .12, .14),
                with_memory=output(.02, .28 if index == 1 else .08, .24 if index == 3 else .07))
            cases.append(case)
            if part == 0:
                cases.append({**case, 'sample_id': case['sample_id'] + '-view2'})
    return ValidationImport(name='Demo / ' + ('Balanced challenge', 'Review workload', 'Mixed lighting', 'Regression investigation')[index],
        cases=cases, configuration={'synthetic': True, 'inference_executed': False, 'demo_seed': SEED,
            'purpose': 'Illustrative matched results, generated locally; no observed model or factory performance.',
            'provenance': 'Virtual lots and sessions are separate from the operational demo lots.',
            'labels': 'Staged truth and predictions; not independently adjudicated.'})


def seed_demo(store, media, *, team_id: str, apply: bool = False, retime_existing: bool = False) -> dict:
    """Preview by default. Caller must explicitly opt into the additive write.

    New records are spread over the past four weeks. retime_existing also moves seeded records written by an
    earlier run, including any visitor edits to them, so it is an explicit operator choice.
    """
    run_started = now()
    actor = _identity(store, team_id)
    pilot = PilotStore(store.engine)
    # Fail closed before writing if our operator namespace is already in use.
    with store.engine.connect() as c:
        existing = c.execute(sa.select(tables.records.c.payload).where(
            tables.records.c.owner_id == team_id, tables.records.c.id.startswith(PREFIX))).scalars()
        if any(record.get('demo_seed') != SEED for record in existing):
            raise ValueError('Refusing to overwrite a record outside this demo seed.')
    if not apply:
        return {'applied': False, 'sample_records': dict(COUNTS), 'note': 'Additive; existing IDs and visitor edits are preserved.'}
    for recipe in PRODUCTS:
        base = PREFIX + recipe['key']
        product, _ = _ensure(pilot, team_id, actor, 'product', base + '-product', {
            'code': recipe['code'], 'name': recipe['name'], 'factory': recipe['area'] + ' / Demo Factory',
            'description': 'Synthetic demonstration. ' + recipe['description']})
        spec = f'ILLUSTRATIVE SAMPLE SPECIFICATION: {recipe["name"]}.\n' + '\n'.join(
            f'{i}. {description}' for i, (_, _, description) in enumerate(recipe['defects'], 1))
        taxonomy = {'part_name': recipe['name'], 'part_width_mm': None, 'source': 'rules', 'classes': [
            {'defect_type': defect, 'label': label, 'clause': str(i), 'description': description, 'limit_mm': None}
            for i, (defect, label, description) in enumerate(recipe['defects'], 1)]}
        for label, status in [('Demo A / superseded', 'retired'), ('Demo C / next draft', 'draft'), ('Demo B / current', 'approved')]:
            revision, _ = _ensure(pilot, team_id, actor, 'revision', base + '-revision-' + status, {
                'product_id': product['id'], 'label': label, 'status': status,
                'spec_text': spec + ('\nDraft proposal: add an additional oblique verification view.' if status == 'draft' else ''),
                'taxonomy': taxonomy, 'taxonomy_confirmed': status != 'draft',
                'capture_instructions': recipe['setup'],
                'approval_note': 'Illustrative lifecycle state; no live administrative approval is asserted.'})
        stations = []
        for number in (1, 2):
            station, _ = _ensure(pilot, team_id, actor, 'station', base + f'-station-{number}', {
                'product_id': product['id'], 'name': f'Demo {recipe["area"]} / {"primary" if number == 1 else "verification"}',
                'instructions': f'Sample station: {recipe["setup"]} ' +
                    ('Use the primary marked position.' if number == 1 else 'Use the second marked position for a verification view.'),
                'active': True})
            stations.append(station)
        for stage in (1, 2, 3):
            station = stations[1 if stage == 2 else 0]
            lot, _ = _ensure(pilot, team_id, actor, 'lot', base + f'-lot-{stage:02d}', {
                'reference': f'DEMO-{recipe["key"].upper()}-{stage:02d}',
                'revision_id': revision['id'], 'station_id': station['id'], 'status': 'open',
                'notes': 'Synthetic sample lot / ' + ('completed dispositions and linked retake' if stage == 1 else
                    'verification station with reviews in progress' if stage == 2 else 'active shift with a held part and open issue')})
            # A visitor may have closed a seeded lot or retired its recipe. Never reopen it.
            captures = []
            if lot['status'] == 'open' and revision['status'] == 'approved' and station['active']:
                for number in range(1, 11):
                    inspection, new = _capture(store, media, pilot, team_id, actor, product, recipe, revision, station, lot, number)
                    captures.append(inspection)
                    if new:
                        _disposition(pilot, team_id, actor, inspection, number, stage == 1)
                    if stage == 1 and number == 6:
                        replacement, new = _capture(store, media, pilot, team_id, actor, product, recipe, revision,
                            station, lot, number, retake=inspection['pilot']['capture_id'])
                        if new:
                            _disposition(pilot, team_id, actor, replacement, number, True, replacement=True)
                if stage == 1:
                    for index, inspection in enumerate(captures[1:5]):
                        _standard(store, pilot, team_id, actor, inspection, index, recipe)
                _issue(pilot, team_id, actor, recipe, lot, captures[1], stage)
                if stage == 1 and lot['version'] == 1:
                    attempts = [c for c in pilot.list(team_id, 'capture') if c['lot_id'] == lot['id']]
                    reviews = [r for r in pilot.list(team_id, 'review') if r['lot_id'] == lot['id']]
                    inspections = {c['inspection_id']: store.inspection(c['inspection_id'])
                                   for c in attempts if c.get('inspection_id')}
                    resolution = lot_resolution(attempts, reviews, inspections)
                    if not (resolution['pending_capture_ids'] or resolution['pending_review_ids'] or resolution['unresolved_parts']):
                        pilot.update(team_id, lot['id'], lot['version'], {'status': 'closed'}, actor)
    for index in range(4):
        id = PREFIX + f'validation-{index}'
        if optional(pilot, team_id, id, 'validation') is None:
            result = evaluate_validation(_validation(index))
            _ensure(pilot, team_id, actor, 'validation', id, {**result, 'created_by': actor})
    retimed = _timeline(store, team_id, since=None if retime_existing else run_started)
    return {'applied': True, 'sample_records': dict(COUNTS), 'retimed': retimed,
            'totals': {kind: len(pilot.list(team_id, kind)) for kind in COUNTS}}


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _timeline(store, team: str, anchor: datetime | None = None, since: str | None = None) -> int:
    """Spread the seeded records over the past four weeks, once, so trends read like a working month.

    Lots open in turn: completed lots first, then lots under review, then the active shift. Captures follow
    their lot at 35-minute intervals, reviews close 90 minutes later, issues open six hours into the lot.
    Records already moved, any record outside this seed and, when `since` is given, any record written before
    `since` are left as they are.
    """
    anchor = (anchor or datetime.now(timezone.utc)).replace(minute=0, second=0, microsecond=0)
    start = anchor - timedelta(days=SPAN_DAYS)
    records = tables.records
    with store.engine.begin() as c:
        query = sa.select(records.c.id, records.c.kind, records.c.payload).where(records.c.owner_id == team)
        if since is not None:
            query = query.where(records.c.created_at >= since)
        rows = {r.id: r for r in c.execute(query)}
        if not any(r.id.startswith(PREFIX) and (r.payload or {}).get('demo_timeline') != TIMELINE for r in rows.values()):
            return 0
        opened, slots, times = {}, {}, {}
        for p_index, recipe in enumerate(PRODUCTS):
            base = PREFIX + recipe['key']
            for offset, suffix in enumerate(('-product', '-revision-retired', '-revision-approved', '-revision-draft',
                                             '-station-1', '-station-2')):
                times[base + suffix] = (start - timedelta(days=3) + timedelta(hours=p_index * 2 + offset), None)
            times[base + '-revision-draft'] = (anchor - timedelta(days=2, hours=p_index), None)
            for stage in (1, 2, 3):
                slot = (stage - 1) * len(PRODUCTS) + p_index
                when = start + timedelta(hours=slot * SPAN_DAYS * 24 / (3 * len(PRODUCTS)) + 7)
                opened[base + f'-lot-{stage:02d}'] = when
                slots[base + f'-lot-{stage:02d}'] = slot
                times[base + f'-lot-{stage:02d}'] = (when, None)
                times[base + f'-issue-{stage:02d}'] = (when + timedelta(hours=6), when + timedelta(days=1, hours=2))
        captured = {}
        for id, row in rows.items():
            if row.kind != 'capture' or not id.startswith(PREFIX):
                continue
            match = re.search(r'-(\d{3})(-retake)?$', id)
            lot_id = (row.payload or {}).get('lot_id')
            lot = opened.get(lot_id)
            if match and lot:
                # Lines run at different paces, so a lot's parts land over a few hours to a day and a half.
                pace = 40 + 37 * (slots[lot_id] % 5)
                when = lot + timedelta(minutes=pace * int(match.group(1))) + (timedelta(hours=3) if match.group(2) else timedelta())
                times[id] = (when, when + timedelta(minutes=2))
                if (row.payload or {}).get('inspection_id'):
                    captured[row.payload['inspection_id']] = when
        for index in range(4):
            times[PREFIX + f'validation-{index}'] = (anchor - timedelta(days=(4 - index) * 5, hours=3), None)
        for id, row in rows.items():
            inspection = (row.payload or {}).get('inspection_id')
            if row.kind == 'review' and inspection in captured:
                closed = (row.payload or {}).get('status') == 'closed'
                times[id] = (captured[inspection], captured[inspection] + timedelta(minutes=90 if closed else 1))
            elif row.kind == 'standard' and inspection in captured:
                times[id] = (captured[inspection] + timedelta(days=1), captured[inspection] + timedelta(days=1, hours=4))
        moved = 0
        for id, (created, updated) in times.items():
            row = rows.get(id)
            if row is None or (row.payload or {}).get('demo_timeline') == TIMELINE:
                continue
            payload = {**row.payload, 'demo_timeline': TIMELINE}
            changed = _stamp(updated or created)
            for key in ('closed_at',):
                if payload.get(key):
                    payload[key] = changed
            if isinstance(payload.get('history'), list):
                payload['history'] = [{**entry, 'at': changed} if isinstance(entry, dict) and 'at' in entry else entry
                                      for entry in payload['history']]
            c.execute(records.update().where(records.c.owner_id == team, records.c.id == id).values(
                created_at=_stamp(created), updated_at=changed, payload=payload))
            moved += 1
        # Events sit just after the record they describe.
        for id, row in rows.items():
            target = (row.payload or {}).get('target_id')
            if row.kind == 'event' and target in times and (row.payload or {}).get('demo_timeline') != TIMELINE:
                created, updated = times[target]
                when = _stamp((updated or created) + timedelta(seconds=30))
                c.execute(records.update().where(records.c.owner_id == team, records.c.id == id).values(
                    created_at=when, updated_at=when, payload={**row.payload, 'demo_timeline': TIMELINE}))
                moved += 1
        # The inspection rows behind seeded captures share the capture time.
        inspections = db.inspections
        for inspection_id, when in captured.items():
            payload = c.execute(sa.select(inspections.c.payload).where(inspections.c.id == inspection_id)).scalar()
            if payload is not None and payload.get('demo_seed') == SEED:
                c.execute(inspections.update().where(inspections.c.id == inspection_id).values(
                    created_at=_stamp(when), payload={**payload, 'created_at': _stamp(when)}))
    return moved
