"""Protect the correction loop: durable state, scope isolation and honest memory failures."""
import importlib
import io
import json

import httpx
import pytest
from PIL import Image


def modules():
    return (importlib.import_module('app.workspace.store'),
            importlib.import_module('app.workspace.memory'),
            importlib.import_module('app.workspace.service'))


def scope(factory='Bangalore Foods', spec='Reject every ink marking.'):
    store, _, _ = modules()
    return store.Scope(factory=factory, part_family='Whole hazelnut', spec_text=spec)


def photo():
    out = io.BytesIO()
    Image.new('RGB', (80, 80), (150, 95, 50)).save(out, 'PNG')
    return out.getvalue()


def fixture_store(tmp_path):
    sm, _, _ = modules()
    return sm.Store(tmp_path / 'workspace.sqlite3')


def add_inspection(store, s, id='i-one'):
    store.add_inspection({'id': id, 'scope_id': s.id, 'factory': s.factory, 'part_family': s.part_family,
                          'spec_text': s.spec_text, 'image_sha256': 'abc', 'filename': 'part.png',
                          'verdict': 'good', 'type': 'good', 'rationale': 'A smooth highlight.',
                          'image_url': '/files/inspections/i-one.jpg', 'memory_enabled': False,
                          'memories': [], 'confidence': 0.8, 'ms': 12, 'cost_usd': 0.001,
                          'created_at': '2026-11-07T12:00:00+00:00'})


def test_correction_and_original_reasoning_survive_a_store_restart(tmp_path):
    st = fixture_store(tmp_path)
    s = scope()
    add_inspection(st, s)
    c = st.add_correction('i-one', verdict='defect', defect_type='print',
                          rule_text='Sharp white letters are ink, not natural gloss.', reviewer='Anika')
    sm, _, _ = modules()
    restored = sm.Store(tmp_path / 'workspace.sqlite3')
    got = restored.corrections(s.id)[0]
    assert got['id'] == c['id']
    assert got['original_rationale'] == 'A smooth highlight.'
    assert got['rule_text'] == 'Sharp white letters are ink, not natural gloss.'
    assert got['sync_status'] == 'pending'
    assert restored.inspection('i-one')['verdict'] == 'good'


def test_factory_and_spec_revision_do_not_share_a_memory_bank():
    a = scope()
    assert a.bank_id != scope(factory='Other factory').bank_id
    assert a.bank_id != scope(spec='Reject cracks only.').bank_id
    assert a.bank_id == scope(factory='  Bangalore Foods  ').bank_id


def test_missing_inspection_cannot_be_corrected(tmp_path):
    st = fixture_store(tmp_path)
    with pytest.raises(KeyError):
        st.add_correction('not-real', verdict='good', defect_type='good', rule_text='Accept.', reviewer='Anika')


def test_a_correction_is_immutable_instead_of_leaving_conflicting_remote_rules(tmp_path):
    st = fixture_store(tmp_path)
    add_inspection(st, scope())
    st.add_correction('i-one', verdict='defect', defect_type='print', rule_text='Reject ink.', reviewer='Anika')
    with pytest.raises(ValueError):
        st.add_correction('i-one', verdict='good', defect_type='good', rule_text='Accept ink.', reviewer='Anika')


def test_retain_uses_stable_document_id_and_preserves_the_human_rule(tmp_path):
    st = fixture_store(tmp_path)
    s = scope()
    add_inspection(st, s)
    c = st.add_correction('i-one', verdict='defect', defect_type='print', rule_text='Reject sharp white letters.', reviewer='Anika')
    _, mm, _ = modules()
    captured = []
    def respond(req):
        captured.append((req.url.path, json.loads(req.content)))
        return httpx.Response(200, json={'success': True, 'bank_id': s.bank_id, 'items_count': 1})
    mem = mm.HindsightMemory('https://memory.example', 'private-key', transport=httpx.MockTransport(respond))
    mem.retain(s, c)
    mem.retain(s, c)
    first, second = captured[0][1]['items'][0], captured[1][1]['items'][0]
    assert first['document_id'] == second['document_id'] == c['id']
    assert first['metadata']['correction_id'] == c['id']
    assert 'Reject sharp white letters.' in first['content']
    assert 'A smooth highlight.' in first['content']
    assert captured[0][1]['async'] is False
    assert captured[0][0] == f'/v1/default/banks/{s.bank_id}/memories'


def test_failed_retain_keeps_correction_pending_and_retry_can_sync_it(tmp_path):
    st = fixture_store(tmp_path)
    s = scope()
    add_inspection(st, s)
    _, mm, service = modules()
    responses = [503, 200]
    def respond(req):
        code = responses.pop(0)
        return httpx.Response(code, json={'success': code == 200, 'items_count': 1})
    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(respond))
    svc = service.WorkspaceService(st, memory, media_root=tmp_path / 'images')
    c = svc.correct('i-one', verdict='defect', defect_type='print', rule_text='Reject ink.', reviewer='Anika')
    assert c['sync_status'] == 'pending'
    assert c['sync_error']
    retried = svc.sync_correction(c['id'])
    assert retried['sync_status'] == 'synced'
    assert retried['sync_error'] is None


def test_memory_off_does_not_call_hindsight_and_does_not_change_the_base_spec(tmp_path, monkeypatch):
    st = fixture_store(tmp_path)
    _, mm, service = modules()
    def no_network(req):
        pytest.fail('Memory-off inspection must not contact Hindsight.')
    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(no_network))
    observed = []
    def inspector(img, spec_text, types, **kw):
        observed.append((spec_text, kw.get('memory_context', [])))
        return {'verdict': 'good', 'defect': False, 'type': 'good', 'confidence': 0.8,
                'rationale': 'Natural gloss.', 'box_px': None, 'mask': None, 'ms': 5, 'cost_usd': 0.001}
    svc = service.WorkspaceService(st, memory, inspector=inspector, media_root=tmp_path / 'images')
    s = scope()
    result = svc.run(photo(), 'part.png', s, use_memory=False)
    assert observed == [('Reject every ink marking.', [])]
    assert result['memory_status'] == 'disabled'
    assert st.inspection(result['id'])['image_sha256']


def test_only_recalled_facts_with_a_known_scoped_correction_enter_the_inspection(tmp_path):
    st = fixture_store(tmp_path)
    s = scope()
    add_inspection(st, s)
    c = st.add_correction('i-one', verdict='defect', defect_type='print', rule_text='Reject white characters.', reviewer='Anika')
    st.mark_sync(c['id'], 'synced')
    other = scope(factory='Other factory')
    add_inspection(st, other, 'i-other')
    outsider = st.add_correction('i-other', verdict='good', defect_type='good', rule_text='Accept all.', reviewer='X')
    _, mm, service = modules()
    facts = [{'id': 'f1', 'text': 'Reject white characters.', 'type': 'world', 'document_id': c['id']},
             {'id': 'f2', 'text': 'Accept all.', 'type': 'world', 'document_id': outsider['id']}]
    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'results': facts})))
    seen = []
    def inspector(img, spec_text, types, **kw):
        seen.extend(kw.get('memory_context', []))
        return {'verdict': 'defect', 'defect': True, 'type': 'print', 'confidence': 0.9,
                'rationale': 'White ink.', 'box_px': [1, 1, 10, 10], 'mask': None, 'ms': 5, 'cost_usd': 0.001}
    svc = service.WorkspaceService(st, memory, inspector=inspector, media_root=tmp_path / 'images')
    result = svc.run(photo(), 'part.png', s, use_memory=True)
    assert [f['text'] for f in seen] == ['Reject white characters.']
    assert result['memories'][0]['source_id'] == c['id']
    assert result['memory_status'] == 'recalled'


def test_a_recall_outage_does_not_silently_fall_back_to_a_memory_on_result(tmp_path):
    st = fixture_store(tmp_path)
    _, mm, service = modules()
    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(lambda req: httpx.Response(503)))
    memory.sleep = lambda seconds: None
    def never_inspect(*args, **kwargs):
        pytest.fail('A failed required recall must be shown before model inspection.')
    svc = service.WorkspaceService(st, memory, inspector=never_inspect, media_root=tmp_path / 'images')
    with pytest.raises(mm.MemoryUnavailable):
        svc.run(photo(), 'part.png', scope(), use_memory=True)
    assert st.inspections(scope().id) == []


def test_unsuccessful_retain_response_is_not_reported_as_synced():
    _, mm, _ = modules()
    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'success': False})))
    with pytest.raises(mm.MemoryUnavailable):
        memory.retain(scope(), {'id': 'c-one', 'rule_text': 'Reject ink.', 'original_rationale': 'Gloss.',
                                'verdict': 'defect', 'defect_type': 'print', 'reviewer': 'A', 'inspection_id': 'i-one'})


def test_recalled_rule_reaches_the_real_inspector_without_rewriting_the_spec(monkeypatch):
    from app.inspect import inspector
    captured = []
    def model(messages, schema, name, **kwargs):
        captured.extend(messages)
        return {'data': {'defect': False, 'type': 'good', 'has_box': False,
                         'x0': 0, 'y0': 0, 'x1': 0, 'y1': 0,
                         'confidence': 0.8, 'rationale': 'Natural texture.'}, 'ms': 1, 'cost_usd': 0.001}
    monkeypatch.setattr(inspector, 'spark_json', model)
    base_spec = 'Reject every ink marking.'
    inspector.inspect(Image.new('RGB', (30, 30)), base_spec, ['print'], with_mask=False,
                      memory_context=[{'source_id': 'correction-123', 'text': 'Sharp white characters are ink.'}])
    system, user = captured
    assert base_spec in system['content']
    recalled = user['content'][-1]['text']
    assert 'correction-123' in recalled
    assert 'Sharp white characters are ink.' in recalled


def test_comparison_identifies_reused_correction_images_and_keeps_arms_paired(tmp_path):
    st = fixture_store(tmp_path)
    _, mm, service = modules()
    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'results': []})))
    def inspector(img, spec, types, **kw):
        return {'verdict': 'good', 'defect': False, 'type': 'good', 'confidence': 0.8,
                'rationale': 'Natural texture.', 'box_px': None, 'mask': None, 'ms': 1, 'cost_usd': 0.001}
    svc = service.WorkspaceService(st, memory, inspector=inspector, media_root=tmp_path / 'images')
    s = scope()
    first = svc.run(photo(), 'part.png', s, use_memory=False)
    svc.correct(first['id'], verdict='defect', defect_type='print', rule_text='Reject white ink.', reviewer='A')
    result = svc.compare(photo(), 'renamed.png', s, expected_verdict='defect')
    assert result['held_out'] is False
    assert result['baseline']['image_sha256'] == result['with_memory']['image_sha256']
    assert result['baseline']['spec_text'] == result['with_memory']['spec_text'] == s.spec_text
    assert result['baseline']['memory_enabled'] is False
    assert result['with_memory']['memory_enabled'] is True


def test_inspector_separates_the_operator_standard_from_an_extracted_fact_about_the_old_mistake(monkeypatch):
    from app.inspect import inspector
    captured = []
    def model(messages, schema, name, **kwargs):
        captured.extend(messages)
        return {'data': {'defect': True, 'type': 'print', 'has_box': True,
                         'x0': 20, 'y0': 20, 'x1': 100, 'y1': 100,
                         'confidence': 0.9, 'rationale': 'White characters are ink.'}, 'ms': 1, 'cost_usd': .001}
    monkeypatch.setattr(inspector, 'spark_json', model)
    inspector.inspect(Image.new('RGB', (100, 100)), 'Reject ink.', ['print'], with_mask=False,
        memory_context=[{'source_id': 'c1', 'text': 'The old inspector called the white letters gloss.',
                         'rule_text': 'Reject white characters as ink.'}])
    record_text = captured[1]['content'][-1]['text'].split('HUMAN QUALITY STANDARDS RECALLED FROM HINDSIGHT:\n')[1]
    record = json.loads(record_text)[0]
    assert record['standard'] == 'Reject white characters as ink.'
    assert record['recalled_evidence'] == 'The old inspector called the white letters gloss.'


def test_metadata_only_copy_is_not_counted_as_a_new_comparison_image(tmp_path):
    from PIL.PngImagePlugin import PngInfo
    st = fixture_store(tmp_path)
    _, mm, service = modules()
    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(lambda req: httpx.Response(200, json={'results': []})))
    def inspector(img, spec, types, **kw):
        return {'verdict': 'good', 'defect': False, 'type': 'good', 'confidence': .8,
                'rationale': 'Texture.', 'box_px': None, 'mask': None, 'ms': 1, 'cost_usd': .001}
    svc = service.WorkspaceService(st, memory, inspector=inspector, media_root=tmp_path / 'images')
    first = svc.run(photo(), 'original.png', scope(), use_memory=False)
    svc.correct(first['id'], verdict='defect', defect_type='print', rule_text='Reject white ink.', reviewer='A')
    metadata = PngInfo(); metadata.add_text('description', 'The identical photo with a new label')
    copy = io.BytesIO(); Image.open(io.BytesIO(photo())).save(copy, 'PNG', pnginfo=metadata)
    result = svc.compare(copy.getvalue(), 'copy.png', scope(), expected_verdict='defect')
    assert result['held_out'] is False


def test_a_missing_hindsight_route_is_not_treated_as_empty_memory():
    _, mm, _ = modules()
    memory = mm.HindsightMemory('https://wrong.example', transport=httpx.MockTransport(
        lambda request: httpx.Response(404, json={'detail': 'Not Found'})))
    with pytest.raises(mm.MemoryUnavailable):
        memory.recall(scope())


def test_hindsight_cloud_is_not_configured_without_its_api_key():
    _, mm, _ = modules()
    memory = mm.HindsightMemory('https://api.hindsight.vectorize.io')
    assert memory.configured is False


def test_a_recognized_missing_hindsight_bank_has_no_corrections():
    _, mm, _ = modules()
    memory = mm.HindsightMemory('https://memory.example', transport=httpx.MockTransport(
        lambda request: httpx.Response(404, json={'detail': f"Bank '{scope().bank_id}' not found"})))
    assert memory.recall(scope()) == []


def test_history_does_not_silently_drop_older_records(tmp_path):
    st = fixture_store(tmp_path)
    s = scope()
    for i in range(101):
        add_inspection(st, s, id=f'i-{i}')
    for i in range(51):
        st.add_comparison({'id': f'pair-{i}', 'scope_id': s.id, 'created_at': f'2026-11-07T12:{i:02d}:00Z'})
    assert len(st.inspections(s.id)) == 101
    assert len(st.comparisons(s.id)) == 51


def test_variants_of_the_same_source_photo_are_disclosed_in_comparisons(tmp_path):
    st = fixture_store(tmp_path)
    _, mm, service = modules()
    memory = mm.HindsightMemory('https://memory.example', transport=httpx.MockTransport(
        lambda req: httpx.Response(200, json={'success': True, 'results': []})))
    def inspector(img, spec, types, **kw):
        return {'verdict': 'good', 'type': 'good', 'rationale': 'Texture.', 'confidence': .8, 'ms': 1, 'cost_usd': 0}
    svc = service.WorkspaceService(st, memory, inspector=inspector, media_root=tmp_path / 'images')
    first = svc.run(photo(), 'source.png', scope(), use_memory=False,
                    source_kind='synthetic_sample', source_group='source-photo-1')
    svc.correct(first['id'], verdict='defect', defect_type='print', rule_text='Reject ink markings.', reviewer='QA')
    second = io.BytesIO(); Image.new('RGB', (80, 80), 'blue').save(second, 'PNG')
    pair = svc.compare(second.getvalue(), 'variant.png', scope(), source_group='source-photo-1')
    assert pair['baseline']['image_sha256'] != first['image_sha256']
    assert pair['held_out'] is False
    assert pair['reuse_reason'] == 'shared_source_photo'
    independent = svc.compare(second.getvalue(), 'other.png', scope(), source_group='source-photo-2')
    assert independent['held_out'] is True


def test_a_late_failed_sync_retry_cannot_revert_a_successful_retain(tmp_path):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    st = fixture_store(tmp_path)
    add_inspection(st, scope())
    correction = st.add_correction('i-one', verdict='defect', defect_type='print',
                                   rule_text='Reject printed ink.', reviewer='QA')
    _, mm, service = modules()
    failed_request_started = threading.Event()
    release_failure = threading.Event()

    def respond(request):
        if not failed_request_started.is_set():
            failed_request_started.set()
            assert release_failure.wait(timeout=5)
            return httpx.Response(503)
        return httpx.Response(200, json={'success': True, 'items_count': 1})

    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(respond))
    svc = service.WorkspaceService(st, memory, media_root=tmp_path / 'images')
    with ThreadPoolExecutor(max_workers=2) as workers:
        late_failure = workers.submit(svc.sync_correction, correction['id'])
        try:
            assert failed_request_started.wait(timeout=5)
            successful = workers.submit(svc.sync_correction, correction['id']).result(timeout=5)
        finally:
            release_failure.set()
        late_result = late_failure.result(timeout=5)

    assert successful['sync_status'] == 'synced'
    assert late_result['sync_status'] == 'synced'
    saved = st.correction(correction['id'])
    assert saved['sync_status'] == 'synced'
    assert saved['sync_error'] is None


def scripted_memory(*responses):
    """Hindsight that answers each request with the next scripted response and records sleeps instead of waiting."""
    _, mm, _ = modules()
    queue, requests, slept = list(responses), [], []
    def respond(req):
        requests.append(req.url.path)
        return queue.pop(0)
    memory = mm.HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(respond))
    memory.sleep = slept.append
    return memory, requests, slept


def test_a_single_rate_limit_on_recall_is_retried():
    fact = {'id': 'f1', 'text': 'Reject ink.', 'type': 'world', 'document_id': 'correction-1'}
    memory, requests, slept = scripted_memory(httpx.Response(429), httpx.Response(200, json={'results': [fact]}))
    assert [f['source_id'] for f in memory.recall(scope())] == ['correction-1']
    assert len(requests) == 2
    assert slept == [1.0]


def test_a_sustained_rate_limit_on_recall_still_fails_with_the_busy_message():
    _, mm, _ = modules()
    memory, requests, slept = scripted_memory(*[httpx.Response(429) for _ in range(3)])
    with pytest.raises(mm.MemoryUnavailable, match='busy'):
        memory.recall(scope())
    assert len(requests) == 3
    assert len(slept) == 2


def test_a_server_error_on_recall_is_not_retried():
    _, mm, _ = modules()
    memory, requests, slept = scripted_memory(httpx.Response(500))
    with pytest.raises(mm.MemoryUnavailable):
        memory.recall(scope())
    assert len(requests) == 1
    assert slept == []


def test_a_long_retry_after_is_capped_so_an_inspection_does_not_hang():
    memory, _, slept = scripted_memory(httpx.Response(429, headers={'retry-after': '30'}),
                                       httpx.Response(200, json={'results': []}))
    assert memory.recall(scope()) == []
    assert slept == [4.0]


def test_a_retry_after_date_falls_back_to_the_default_wait():
    memory, _, slept = scripted_memory(httpx.Response(429, headers={'retry-after': 'Wed, 21 Oct 2026 07:28:00 GMT'}),
                                       httpx.Response(200, json={'text': 'Reject ink.', 'facts': []}))
    assert memory.reflect(scope())['summary'] == 'Reject ink.'
    assert slept == [1.0]


def test_a_rate_limited_retain_is_left_to_the_outbox():
    _, mm, _ = modules()
    memory, requests, slept = scripted_memory(httpx.Response(429), httpx.Response(200, json={'success': True}))
    with pytest.raises(mm.MemoryUnavailable, match='busy'):
        memory.retain(scope(), {'id': 'c-one', 'rule_text': 'Reject ink.', 'original_rationale': 'Gloss.',
                                'verdict': 'defect', 'defect_type': 'print', 'reviewer': 'A', 'inspection_id': 'i-one'})
    assert len(requests) == 1
    assert slept == []
