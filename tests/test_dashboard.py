"""The dashboard counts decisions, defects, corrections, memory use, cost and latency for one scope."""
from test_workspace_api import png, setup_client


def test_the_dashboard_summarises_a_scope(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    verdicts = iter(['defect', 'defect', 'good', 'uncertain'])

    def inspector(img, spec, types, **kw):
        verdict = next(verdicts)
        return {'verdict': verdict, 'defect': verdict == 'defect', 'type': 'crack' if verdict == 'defect' else 'good',
                'confidence': .8, 'rationale': 'r', 'box_px': None, 'mask': None, 'ms': 1000 * (len(kw) + 1),
                'cost_usd': .004}

    routes.service.inspector = inspector
    items = [client.post('/api/workspace/inspect', files={'file': ('p.png', png(), 'image/png')},
                         data={'memory_enabled': 'false'}).json() for _ in range(4)]
    client.post('/api/workspace/corrections', json={'inspection_id': items[2]['id'], 'verdict': 'defect',
                                                    'defect_type': 'print', 'rule_text': 'White letters are ink.', 'reviewer': 'QA'})
    board = client.get('/api/workspace/dashboard', params={'days': 7}).json()
    totals = board['totals']
    assert (totals['inspections'], totals['rejected'], totals['accepted'], totals['review']) == (4, 2, 1, 1)
    assert totals['reject_rate'] == 0.5
    assert totals['corrections'] == 1 and totals['overturned'] == 1
    assert totals['cost_per_inspection'] == 0.004
    assert board['pareto'] == [{'defect_type': 'crack', 'label': 'Crack', 'clause': '4.2', 'count': 2, 'share': 1.0}]
    assert sum(d['inspections'] for d in board['daily']) == 4
    assert len(board['daily']) == 8
    assert board['corrections_weekly'][0]['corrections'] == 1


def test_another_scope_is_not_counted(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    client.post('/api/workspace/inspect', files={'file': ('p.png', png(), 'image/png')}, data={'memory_enabled': 'false'})
    other = client.get('/api/workspace/dashboard', params={'factory': 'Other plant'}).json()
    assert other['totals']['inspections'] == 0
    assert other['totals']['reject_rate'] is None


def test_comparison_arms_do_not_inflate_production_assessment_counts(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    response = client.post('/api/workspace/compare', files={'file': ('p.png', png(), 'image/png')})
    assert response.status_code == 200
    client.post('/api/workspace/inspect', files={'file': ('p.png', png(), 'image/png')}, data={'memory_enabled': 'false'})
    board = client.get('/api/workspace/dashboard').json()
    assert board['totals']['inspections'] == 1
    assert board['excluded_evaluation_assessments'] == 2


def test_memory_cited_counts_rationales_that_cite_a_recalled_correction(tmp_path):
    from app.workspace.dashboard import dashboard
    from app.workspace.store import now
    from test_workspace import fixture_store, scope
    store, s = fixture_store(tmp_path), scope()
    cid = 'correction-021bdf864a92418abe76c5e026cef585'
    for n, rationale in enumerate(['Natural texture.', f'White ink, as in {cid}.', 'As in correction-deadbeefdeadbeef.']):
        # Saved without cited_ids, like rows written before citations were recorded.
        store.add_inspection({'id': f'insp-{n}', 'scope_id': s.id, 'factory': s.factory, 'part_family': s.part_family,
                              'spec_text': s.spec_text, 'image_sha256': 'abc', 'filename': 'p.png', 'verdict': 'good',
                              'type': 'good', 'rationale': rationale, 'image_url': '/x.jpg', 'memory_enabled': True,
                              'memories': [{'source_id': cid, 'text': 'Reject ink.'}], 'confidence': .8, 'ms': 1,
                              'cost_usd': .001, 'created_at': now()})
    totals = dashboard(store, s.id, [], 7)['totals']
    assert totals['memory_inspections'] == 3
    assert totals['citation_rate'] == 1 / 3
    assert totals['unknown_citations'] == 1
