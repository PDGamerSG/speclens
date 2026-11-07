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
    prompt = captured[0]['content']
    assert 'correction-123' in prompt
    assert 'Sharp white characters are ink.' in prompt
    assert base_spec in prompt


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
