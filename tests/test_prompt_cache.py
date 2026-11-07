"""Prompt layout rules that keep the Model API prefix cache effective."""
import base64
import json

from PIL import Image

from app.inspect import inspector
from app.meta import ledger


def reply(**overrides):
    data = {'part_visible': True, 'defect': False, 'type': 'good', 'has_box': False, 'x0': 0, 'y0': 0,
            'x1': 0, 'y1': 0, 'confidence': .8, 'rationale': 'Natural texture.'}
    return {'data': {**data, **overrides}, 'ms': 1, 'cost_usd': .001,
            'usage': {'prompt': 1300, 'completion': 40, 'cached': 1200}}


def capture(monkeypatch, **overrides):
    calls = []

    def model(messages, schema, name, **kwargs):
        calls.append({'messages': messages, 'schema': schema, 'kwargs': kwargs})
        return reply(**overrides)

    monkeypatch.setattr(inspector, 'spark_json', model)
    return calls


def part():
    return Image.new('RGB', (40, 40), (120, 80, 40))


def facts(*ids):
    return [{'source_id': i, 'text': f'Fact {i}', 'rule_text': f'Rule {i}'} for i in ids]


def memory_block(messages):
    return next(p['text'] for p in messages[-1]['content'] if p['type'] == 'text' and inspector.MEMORY_HEADING in p['text'])


def test_memory_follows_the_photo_so_both_comparison_arms_share_one_prefix(monkeypatch):
    calls = capture(monkeypatch)
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False)
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False, memory_context=facts('c1'))
    baseline, remembered = calls[0]['messages'], calls[1]['messages']
    assert baseline[0] == remembered[0]
    assert baseline[1]['content'] == remembered[1]['content'][:len(baseline[1]['content'])]
    assert remembered[1]['content'][-1]['type'] == 'text'
    assert inspector.MEMORY_HEADING in remembered[1]['content'][-1]['text']


def test_same_recalled_standards_produce_identical_bytes_in_any_recall_order(monkeypatch):
    calls = capture(monkeypatch)
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False, memory_context=facts('b', 'a', 'c'))
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False, memory_context=facts('c', 'b', 'a'))
    assert memory_block(calls[0]['messages']) == memory_block(calls[1]['messages'])


def test_the_cache_key_names_the_shared_prefix_and_not_the_request(monkeypatch):
    calls = capture(monkeypatch)
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False)
    inspector.inspect(Image.new('RGB', (40, 40), (1, 2, 3)), 'Reject ink.', ['print'], with_mask=False, memory_context=facts('c1'))
    inspector.inspect(part(), 'A different specification.', ['print'], with_mask=False)
    keys = [c['kwargs']['cache_key'] for c in calls]
    assert keys[0] == keys[1]
    assert keys[0] != keys[2]


def test_the_system_message_stays_fixed_for_one_specification(monkeypatch):
    calls = capture(monkeypatch)
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False, memory_context=facts('a'))
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False, memory_context=facts('a', 'b'))
    assert calls[0]['messages'][0] == calls[1]['messages'][0]
    assert 'Reject ink.' in calls[0]['messages'][0]['content']


def test_token_usage_reaches_the_inspection_result(monkeypatch):
    capture(monkeypatch)
    result = inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False)
    assert (result['prompt_tokens'], result['cached_tokens']) == (1300, 1200)


def test_a_photo_without_the_part_needs_human_review_and_has_no_defect_box(monkeypatch):
    calls = capture(monkeypatch, part_visible=False, defect=True, type='print', has_box=True, x0=10, y0=10, x1=500, y1=500,
                    rationale='This photo shows a keyboard, not a hazelnut.')
    result = inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False)
    assert 'part_visible' in calls[0]['schema']['required']
    assert result['verdict'] == 'uncertain'
    assert result['defect'] is False
    assert result['box_px'] is None
    assert result['rationale'] == 'This photo shows a keyboard, not a hazelnut.'


def test_the_photo_payload_is_stable_for_the_same_pixels(monkeypatch):
    calls = capture(monkeypatch)
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False)
    inspector.inspect(part(), 'Reject ink.', ['print'], with_mask=False)
    photo = [p for p in calls[0]['messages'][1]['content'] if p['type'] == 'image_url'][0]
    again = [p for p in calls[1]['messages'][1]['content'] if p['type'] == 'image_url'][0]
    assert photo == again
    assert base64.b64decode(photo['image_url']['url'].split(',', 1)[1])


def test_cache_stats_report_reuse_and_the_saving_against_the_full_input_price(tmp_path, monkeypatch):
    target = tmp_path / 'ledger.jsonl'
    target.write_text('\n'.join(json.dumps(row) for row in [
        {'model': 'muse-spark-1.3', 'op': 'inspect', 'status': 200, 'prompt_tokens': 1000, 'cached_tokens': 800, 'cost_usd': .001},
        {'model': 'muse-spark-1.3', 'op': 'inspect', 'status': 200, 'prompt_tokens': 1000, 'cached_tokens': 0, 'cost_usd': .002},
        {'model': 'sam-3.1', 'op': 'mask', 'status': 200, 'cost_usd': .0025},
    ]))
    monkeypatch.setattr(ledger, 'LEDGER', target)
    stats = ledger.cache_stats()
    assert stats['prompt_tokens'] == 2000
    assert stats['cached_tokens'] == 800
    assert stats['hit_rate'] == .4
    assert stats['saved_usd'] == round(800 * (1.25e-6 - .15e-6), 6)
