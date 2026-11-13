"""Any specification drives the inspection: its reject classes, clauses, limits and part width."""
import pytest

from app.forge.spec import DEFAULT_SPEC
from app.workspace.spec import parse_spec
from test_workspace_api import png, setup_client

PCB = """PCB VISUAL INSPECTION STANDARD PCB-QA-2 rev A
Part: assembled controller board, 80 mm wide.
2 ACCEPTABLE
2.1 Minor flux residue that is clear and dry.
3 REJECT
3.1 Solder bridge: any solder joining two adjacent pads.
3.2 Scratch - a scratch through solder mask longer than 3 mm.
3.3 Missing component: any empty footprint marked on the silkscreen.
4 RECORDS
4.1 Keep: images for 90 days."""


def minimal_pdf(text: str) -> bytes:
    """A one-page PDF with a single line of text, built by hand so the test needs no PDF writer."""
    stream = f'BT /F1 12 Tf 72 720 Td ({text}) Tj ET'.encode()
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
               b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>',
               b'<< /Length %d >>\nstream\n' % len(stream) + stream + b'\nendstream',
               b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>']
    out, offsets = bytearray(b'%PDF-1.4\n'), []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b'%d 0 obj\n' % number + body + b'\nendobj\n'
    xref = len(out)
    out += b'xref\n0 %d\n0000000000 65535 f \n' % (len(objects) + 1)
    out += b''.join(b'%010d 00000 n \n' % o for o in offsets)
    out += b'trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n' % (len(objects) + 1, xref)
    return bytes(out)


def test_the_hazelnut_spec_reads_as_its_four_reject_clauses():
    t = parse_spec(DEFAULT_SPEC)
    assert [(c['defect_type'], c['clause']) for c in t['classes']] == [('hole', '4.1'), ('crack', '4.2'), ('cut', '4.3'), ('print', '4.4')]
    assert t['part_width_mm'] == 20.0
    assert t['source'] == 'rules'


def test_a_different_part_gets_its_own_classes_and_size_limits():
    t = parse_spec(PCB)
    assert [c['defect_type'] for c in t['classes']] == ['solder_bridge', 'scratch', 'missing_component']
    assert t['classes'][1]['limit_mm'] == 3.0
    assert t['part_width_mm'] == 80.0
    assert t['part_name'] == 'assembled controller board'


def test_a_spec_without_numbered_reject_clauses_still_has_one_class():
    t = parse_spec('Inspect for anything unusual.')
    assert [c['defect_type'] for c in t['classes']] == ['defect']
    assert t['source'] == 'fallback'


def test_inspection_and_correction_follow_the_scope_specification(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    seen = []
    inner = routes.service.inspector
    routes.service.inspector = lambda img, spec, types, **kw: seen.append(types) or inner(img, spec, types, **kw)
    scope = {'factory': 'Board plant', 'part_family': 'Controller board', 'spec_text': PCB}
    item = client.post('/api/workspace/inspect', files={'file': ('board.png', png(), 'image/png')},
                       data={**scope, 'memory_enabled': 'false'}).json()
    assert seen == [['solder_bridge', 'scratch', 'missing_component']]
    overview = client.get('/api/workspace/overview', params=scope).json()
    assert [c['defect_type'] for c in overview['taxonomy']['classes']] == seen[0]
    base = {'inspection_id': item['id'], 'verdict': 'defect', 'rule_text': 'Bridged pads are a reject.', 'reviewer': 'QA'}
    assert client.post('/api/workspace/corrections', json={**base, 'defect_type': 'print'}).status_code == 422
    assert client.post('/api/workspace/corrections', json={**base, 'defect_type': 'solder_bridge'}).status_code == 201


def test_a_pdf_specification_is_read_into_text_and_classes(tmp_path, monkeypatch):
    client, _ = setup_client(tmp_path, monkeypatch)
    pdf = minimal_pdf('4.1 Hole: any hole through the shell. REJECT')
    response = client.post('/api/workspace/specs/extract', files={'file': ('spec.pdf', pdf, 'application/pdf')})
    assert response.status_code == 200
    assert '4.1 Hole' in response.json()['spec_text']
    blank = client.post('/api/workspace/specs/extract', files={'file': ('scan.pdf', minimal_pdf(''), 'application/pdf')})
    assert blank.status_code == 422


def test_the_model_reading_is_saved_for_later_inspections(tmp_path, monkeypatch):
    client, routes = setup_client(tmp_path, monkeypatch)
    calls = []

    def model(spec_text):
        calls.append(spec_text)
        return {'part_name': 'cap', 'part_width_mm': 30, 'defects': [
            {'defect_type': 'Flash', 'clause': '2.1', 'description': 'a thin plastic fin', 'severity_note': 'longer than 0.5 mm'}]}

    monkeypatch.setattr(routes, 'taxonomy_model', model)
    spec = 'Bottle cap spec. Reject moulding flash.'
    reading = client.post('/api/workspace/specs/extract', data={'spec_text': spec, 'use_model': 'true'}).json()
    assert reading['taxonomy']['source'] == 'model'
    assert reading['taxonomy']['classes'][0] == {'defect_type': 'flash', 'label': 'Flash', 'clause': '2.1',
                                                 'description': 'a thin plastic fin', 'limit_mm': 0.5}
    assert client.post('/api/workspace/specs/parse', json={'spec_text': spec}).json()['source'] == 'model'
    assert len(calls) == 1


@pytest.mark.parametrize('spec', ['', 'x' * 12001])
def test_spec_parsing_rejects_empty_or_oversized_text(tmp_path, monkeypatch, spec):
    client, _ = setup_client(tmp_path, monkeypatch)
    assert client.post('/api/workspace/specs/parse', json={'spec_text': spec}).status_code == 422


def test_reading_a_spec_by_rules_does_not_use_the_hourly_limit(tmp_path, monkeypatch):
    from test_public_workspace import public_clients
    import app.public as public
    first, _, _ = public_clients(tmp_path, monkeypatch)
    monkeypatch.setattr(public, 'CALL_LIMIT', 1)
    for _ in range(3):
        assert first.post('/api/workspace/specs/parse', json={'spec_text': PCB}).status_code == 200
    assert first.post('/api/workspace/inspect', data={'sample_id': 'white-print', 'memory_enabled': 'false'}).status_code == 200
