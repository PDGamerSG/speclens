"""Defects are outlined and measured in millimetres, and a correction's crop is shown to the model next time."""
import io

import httpx
import numpy as np
from PIL import Image

from app.inspect import inspector
from app.inspect.measure import measure
from app.workspace.memory import HindsightMemory
from app.workspace.service import WorkspaceService
from app.workspace.store import Scope, Store

SPEC = """CAP SPEC
Part: bottle cap, nominal width 20 mm.
3 REJECT
3.1 Flash: a plastic fin longer than 3 mm.
3.2 Print: any ink marking."""


def defect_mask(length=50):
    mask = np.zeros((300, 300), bool)
    mask[150:153, 100:100 + length] = True
    return mask


def test_a_mask_is_measured_against_the_part_width_and_the_clause_limit():
    m = measure(defect_mask(50), [50, 50, 250, 250], 20.0, 3.0)
    assert 5.0 <= m['length_mm'] <= 5.2, 'a 50 px line on a 200 px, 20 mm part is about 5 mm'
    assert m['within_limit'] is False
    small = measure(defect_mask(20), [50, 50, 250, 250], 20.0, 3.0)
    assert small['within_limit'] is True
    assert measure(defect_mask(50), None, 20.0, 3.0)['length_mm'] is None, 'no part box, no scale'
    assert measure(np.zeros((10, 10), bool), [0, 0, 10, 10], 20.0, None) is None


def service(tmp_path, inspect_fn, memory=None):
    memory = memory or HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={'success': True, 'items_count': 1}) if r.url.path.endswith('/memories')
        else httpx.Response(200, json={'results': []})))
    return WorkspaceService(Store(tmp_path / 'db.sqlite3'), memory, inspector=inspect_fn, media_root=tmp_path / 'media')


def photo():
    out = io.BytesIO()
    Image.new('RGB', (300, 300), (150, 95, 50)).save(out, 'PNG')
    return out.getvalue()


def masked_inspector(length):
    def run(img, spec, types, **kw):
        return {'verdict': 'defect', 'defect': True, 'type': 'flash', 'confidence': .9, 'rationale': 'A fin.',
                'box_px': [100, 140, 100 + length, 160], 'mask': defect_mask(length), 'part_box_px': [50, 50, 250, 250],
                'ms': 1, 'cost_usd': .001}
    return run


def test_a_defect_gets_an_outline_and_a_size_and_a_small_one_goes_to_review(tmp_path):
    scope = Scope('Cap plant', 'Cap', SPEC)
    big = service(tmp_path, masked_inspector(50)).run(photo(), 'cap.png', scope, use_memory=False)
    assert big['verdict'] == 'defect'
    assert big['measurement']['length_mm'] > 3
    assert big['overlay_url'].endswith('_overlay.jpg')
    svc = service(tmp_path, masked_inspector(20))
    small = svc.run(photo(), 'cap.png', scope, use_memory=False)
    assert small['verdict'] == 'uncertain'
    assert 'within the 3.0 mm limit of clause 3.1' in small['size_note']
    assert svc.media.get(f'{small["id"]}_mask.png') and svc.media.get(f'{small["id"]}_overlay.jpg')


def test_the_outline_is_served_only_to_its_owner(tmp_path, monkeypatch):
    from test_public_workspace import public_clients
    first, second, routes = public_clients(tmp_path, monkeypatch)
    routes.service.inspector = masked_inspector(50)
    item = first.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'}).json()
    assert first.get(item['overlay_url']).status_code == 200
    assert first.get(item['mask_url']).headers['content-type'] == 'image/png'
    assert second.get(item['overlay_url']).status_code == 404


def test_a_correction_keeps_its_crop_and_the_next_recall_shows_it_to_the_model(tmp_path):
    facts = {}

    def respond(request):
        if request.url.path.endswith('/memories'):
            item = __import__('json').loads(request.content)['items'][0]
            facts[item['document_id']] = {'id': 'f-' + item['document_id'], 'text': 'Fins are flash.',
                                          'document_id': item['document_id']}
            return httpx.Response(200, json={'success': True, 'items_count': 1})
        return httpx.Response(200, json={'results': list(facts.values())})

    seen = []

    def inspect_fn(img, spec, types, **kw):
        seen.append(kw)
        return masked_inspector(50)(img, spec, types)

    memory = HindsightMemory('https://memory.example', 'key', transport=httpx.MockTransport(respond))
    svc = service(tmp_path, inspect_fn, memory)
    scope = Scope('Cap plant', 'Cap', SPEC)
    first = svc.run(photo(), 'cap.png', scope, use_memory=False)
    correction = svc.correct(first['id'], verdict='defect', defect_type='flash', rule_text='Fins are flash.', reviewer='QA')
    assert correction['crop_url'] == f'/files/workspace/{correction["id"]}_crop.jpg'
    crop = Image.open(io.BytesIO(svc.media.get(f'{correction["id"]}_crop.jpg')))
    assert max(crop.size) <= 384
    second = svc.run(photo(), 'cap.png', scope, use_memory=True)
    references = seen[-1]['memory_exemplars']
    assert len(references) == 1 and correction['id'] in references[0][0]
    assert second['reference_crops'] == [correction['id']]


def test_reference_crops_sit_after_the_photo_and_before_the_written_standards(monkeypatch):
    captured = []

    def model(messages, schema, name, **kwargs):
        captured.extend(messages)
        return {'data': {'part_visible': True, 'defect': False, 'type': 'good', 'has_box': False, 'x0': 0, 'y0': 0,
                         'x1': 0, 'y1': 0, 'part_x0': 100, 'part_y0': 100, 'part_x1': 900, 'part_y1': 900,
                         'confidence': .8, 'rationale': 'Fine.'}, 'ms': 1, 'cost_usd': .001}

    monkeypatch.setattr(inspector, 'spark_json', model)
    out = inspector.inspect(Image.new('RGB', (100, 100)), 'Reject fins.', ['flash'], with_mask=False,
                            memory_context=[{'source_id': 'c1', 'text': 'Fins are flash.'}],
                            memory_exemplars=[('Reference crop from correction c1', Image.new('RGB', (40, 40)))])
    parts = captured[1]['content']
    kinds = [p['type'] for p in parts]
    assert kinds == ['text', 'image_url', 'text', 'image_url', 'text']
    assert parts[0]['text'] == 'Inspect this part.'
    assert parts[2]['text'] == 'Reference crop from correction c1'
    assert inspector.MEMORY_HEADING in parts[4]['text']
    assert out['part_box_px'] == [10, 10, 90, 90]
