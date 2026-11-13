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
