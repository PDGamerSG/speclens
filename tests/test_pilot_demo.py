"""A populated public demo must remain isolated, repeatable and provider-free."""
from copy import deepcopy
import io

import httpx
from PIL import Image
import pytest
import sqlalchemy as sa

from app import db
from app.media import LocalMedia
from app.pilot import tables
from app.pilot.integration import correction_approved, eligible_sources
from app.pilot.reports import lot_evidence
from app.pilot.store import PilotStore, now
from app.workspace.memory import HindsightMemory
from app.workspace.service import WorkspaceService
from app.workspace.store import Store


def demo_team(store, name='SpecLens Demo Factory', active=True):
    with store.engine.begin() as c:
        c.execute(tables.teams.insert().values(id='team-demo', name=name, created_at=now()))
        c.execute(tables.users.insert().values(id='user-demo', username='demo.speclens',
            name='Demo Quality Engineer', password_hash='not-a-login-hash', created_at=now()))
        c.execute(tables.memberships.insert().values(id='member-demo', team_id='team-demo',
            user_id='user-demo', role='engineer', active=active, created_at=now()))


def test_staged_corrections_never_enter_memory_even_after_approval(tmp_path):
    from test_pilot_integration import lane, png
    service, pilot, actor, scope, context, observed = lane(tmp_path)
    inspection = service.run(png(), 'sample.png', scope, use_memory=False, context=context())
    service.store.update_inspection(inspection['id'], demo_seed='factory-demo-v1')
    correction = service.correct(inspection['id'], verdict='defect', defect_type='print',
        rule_text='Illustrative sample only.', reviewer=actor['name'])
    standard = pilot.list(scope.owner_id, 'standard')[0]
    pilot.update(scope.owner_id, standard['id'], standard['version'], {'status': 'approved'}, actor)
    assert correction['sync_status'] == 'demo'
    assert standard['demo_seed'] == 'factory-demo-v1'
    assert not correction_approved(service.store, correction)
    assert correction['id'] not in service.store.due_corrections()
    service.sync_correction(correction['id'])
    service.drain_outbox()
    assert observed['retains'] == 0
    # A stale/imported sync flag must not make staged examples eligible either.
    service.store.mark_sync(correction['id'], 'synced')
    assert eligible_sources(service.store, scope) == {}


@pytest.mark.parametrize('name,active,team_id', [
    ('Private factory', True, 'team-demo'),
    ('SpecLens Demo Factory', False, 'team-demo'),
    ('SpecLens Demo Factory', True, 'team-other'),
])
def test_seed_refuses_non_demo_targets_before_writing(tmp_path, name, active, team_id):
    from app.pilot.demo_seed import seed_demo
    store = Store(tmp_path / 'db.sqlite')
    demo_team(store, name, active)
    with pytest.raises(ValueError, match='demo team'):
        seed_demo(store, LocalMedia(tmp_path / 'media'), team_id=team_id, apply=True)
    with store.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(tables.records)) == 0
        assert c.scalar(sa.select(sa.func.count()).select_from(db.inspections)) == 0
    assert not list((tmp_path / 'media').iterdir())


def test_populated_demo_has_complete_reports_and_preserves_user_changes(tmp_path, monkeypatch):
    from app.pilot.demo_seed import seed_demo
    def no_network(*args, **kwargs):
        raise AssertionError('Demo population must not call any provider.')
    monkeypatch.setattr(httpx.Client, 'send', no_network)
    store = Store(tmp_path / 'db.sqlite')
    pilot = PilotStore(store.engine)
    media = LocalMedia(tmp_path / 'media')
    demo_team(store)
    private = pilot.create('team-private', 'product', {'code': 'PRIVATE', 'name': 'Private part'})
    before = deepcopy(pilot.list('team-private', 'event'))
    preview = seed_demo(store, media, team_id='team-demo')
    assert preview['applied'] is False
    assert pilot.list('team-demo', 'product') == []
    assert list((tmp_path / 'media').iterdir()) == []
    result = seed_demo(store, media, team_id='team-demo', apply=True)
    assert result['applied'] is True
    expected = {'product': 6, 'revision': 18, 'station': 12, 'lot': 18,
                'capture': 186, 'review': 186, 'standard': 24, 'nonconformance': 18, 'validation': 4}
    assert {kind: len(pilot.list('team-demo', kind)) for kind in expected} == expected
    assert {r['status'] for r in pilot.list('team-demo', 'revision')} == {'draft', 'approved', 'retired'}
    reviews = pilot.list('team-demo', 'review')
    assert {r['status'] for r in reviews} == {'open', 'claimed', 'closed'}
    assert {r['outcome'] for r in reviews if r.get('outcome')} == {'accept', 'reject', 'hold', 'retake'}
    service = WorkspaceService(store, HindsightMemory(''), media=media)
    for lot in pilot.list('team-demo', 'lot'):
        report = lot_evidence(service, 'team-demo', lot['id'])
        assert report['counts']['physical_parts'] == 10
        assert report['counts']['missing_evidence'] == 0
        assert report['counts']['assessments'] == report['counts']['capture_attempts']
        assert (report['counts']['unresolved_parts'] == 0) == (lot['status'] == 'closed')
        for inspection in report['inspections']:
            assert inspection['source_kind'] == 'synthetic_sample'
            assert inspection['demo_seed']
            assert inspection['cost_usd'] == inspection['ms'] == 0
            assert 'no model' in inspection['rationale'].lower()
            with Image.open(io.BytesIO(media.get(inspection['image_url'].split('/')[-1]))) as image:
                assert image.width >= 640
    assert store.due_corrections(1000, approved_only=True) == []
    for run in pilot.list('team-demo', 'validation'):
        assert run['source'] == 'imported_unverified'
        assert run['configuration']['synthetic'] is True
        assert run['results']['counts']['physical_parts'] >= 200
        assert run['results']['counts']['repeated_views'] > 0
    assert pilot.get('team-private', private['id']) == private
    assert pilot.list('team-private', 'event') == before
    product = pilot.list('team-demo', 'product')[0]
    edited = pilot.update('team-demo', product['id'], product['version'], {'description': 'User edit to keep'})
    review = next(r for r in reviews if r['status'] == 'open')
    changed = pilot.update('team-demo', review['id'], review['version'], {'status': 'claimed', 'assignee': {'name': 'User'}})
    snapshot = {kind: pilot.list('team-demo', kind) for kind in [*expected, 'event']}
    seed_demo(store, media, team_id='team-demo', apply=True)
    assert {kind: pilot.list('team-demo', kind) for kind in snapshot} == snapshot
    assert pilot.get('team-demo', product['id']) == edited
    assert pilot.get('team-demo', review['id']) == changed
    with store.engine.connect() as c:
        assert c.scalar(sa.select(sa.func.count()).select_from(db.model_calls)) == 0


@pytest.mark.parametrize('interruption', ['inspection', 'standard', 'issue'])
def test_interrupted_seed_recovers_incomplete_records_without_overwriting_reviews(tmp_path, monkeypatch, interruption):
    from app.pilot.demo_seed import seed_demo
    store = Store(tmp_path / 'db.sqlite')
    pilot = PilotStore(store.engine)
    media = LocalMedia(tmp_path / 'media')
    demo_team(store)
    if interruption == 'inspection':
        original = store.add_inspection
        def interrupted_write(item):
            original(item)
            raise RuntimeError('Simulated operator disconnect after inspection commit')
        monkeypatch.setattr(store, 'add_inspection', interrupted_write)
    else:
        original = PilotStore.create
        def interrupted_create(self, owner_id, kind, *args, **kwargs):
            result = original(self, owner_id, kind, *args, **kwargs)
            if kind == ('standard' if interruption == 'standard' else 'nonconformance'):
                raise RuntimeError('Simulated operator disconnect after record commit')
            return result
        monkeypatch.setattr(PilotStore, 'create', interrupted_create)
    with pytest.raises(RuntimeError, match='Simulated operator disconnect'):
        seed_demo(store, media, team_id='team-demo', apply=True)
    monkeypatch.undo()
    if interruption != 'inspection':
        # A visitor can edit a partially populated workspace before the operator retries.
        prior = pilot.list('team-demo', 'review')[0]
        edited = pilot.update('team-demo', prior['id'], prior['version'], {'reason': 'Visitor note to preserve'})
    seed_demo(store, media, team_id='team-demo', apply=True)
    assert len(pilot.list('team-demo', 'review')) == 186
    assert all(c['status'] == 'done' for c in pilot.list('team-demo', 'capture'))
    first = pilot.get('team-demo', 'demo-v1-hazelnut-lot-01')
    assert first['status'] == 'closed'
    assert len([s for s in pilot.list('team-demo', 'standard') if s['status'] == 'approved']) == 12
    assert len([i for i in pilot.list('team-demo', 'nonconformance') if i['status'] == 'closed']) == 6
    if interruption != 'inspection':
        assert pilot.get('team-demo', edited['id']) == edited


def test_the_seeded_month_spreads_over_four_weeks_and_feeds_the_overview(tmp_path):
    from collections import Counter
    from app.pilot.demo_seed import seed_demo
    from app.pilot.insights import insights
    store = Store(tmp_path / 'db.sqlite')
    pilot = PilotStore(store.engine)
    demo_team(store)
    result = seed_demo(store, LocalMedia(tmp_path / 'media'), team_id='team-demo', apply=True)
    assert result['retimed'] > 400
    days = Counter(c['created_at'][:10] for c in pilot.list('team-demo', 'capture'))
    assert len(days) >= 15, 'captures land on many days, not one'
    assert seed_demo(store, LocalMedia(tmp_path / 'media'), team_id='team-demo', apply=True)['retimed'] == 0
    view = insights(pilot, store, 'team-demo', days=30)
    assert view['kpis']['captures'] == 186
    assert sum(d['captures'] for d in view['daily']) == 186
    assert sum(1 for d in view['daily'] if d['captures']) >= 15
    assert {row['code'] for row in view['products']} >= {'DEMO-HZ02', 'DEMO-PC01'}
    assert view['kpis']['first_pass_yield']['denominator'] > 0
    assert view['defects'] and view['defects'][0]['flagged'] >= view['defects'][0]['confirmed']
    assert any(item['kind'] == 'issue' for item in view['attention'])
    assert view['kpis']['open_reviews'] > 0
