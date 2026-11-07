"""Local E2E server. Only external vision and Hindsight HTTP transport are simulated."""
import os
import sys
import tempfile
from pathlib import Path

os.environ['MODEL_API_KEY'] = ''
os.environ['DEMO_MODE'] = '1'
os.environ['SPECLENS_VAR'] = tempfile.mkdtemp(prefix='speclens-e2e-')
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))

import json
import httpx
import uvicorn
from app.main import app
from app.workspace import routes
from app.workspace.memory import HindsightMemory

facts = {}


def respond(request):
    body = json.loads(request.content)
    bank = request.url.path.split('/')[4]
    if request.url.path.endswith('/memories'):
        item = body['items'][0]
        rule = item['content'].split('Apply this visual quality standard to future matching parts: ', 1)[1].split('\n', 1)[0]
        facts.setdefault(bank, {})[item['document_id']] = {'id': 'fact-' + item['document_id'],
            'text': rule, 'type': 'world', 'document_id': item['document_id'], 'metadata': item['metadata']}
        return httpx.Response(200, json={'success': True, 'items_count': 1})
    if request.url.path.endswith('/reflect'):
        return httpx.Response(200, json={'text': 'Reject sharp white ink markings. Keep natural shell texture acceptable.', 'facts': []})
    return httpx.Response(200, json={'results': list(facts.get(bank, {}).values())})


def vision(image, spec_text, types, **kwargs):
    memories = kwargs.get('memory_context', [])
    reject = bool(memories)
    return {'verdict': 'defect' if reject else 'good', 'defect': reject,
            'type': 'print' if reject else 'good', 'confidence': .94 if reject else .81,
            'rationale': 'Sharp white characters are ink. Applied correction ' + memories[0]['source_id'] if reject else 'The bright area appears to be natural shell gloss.',
            'box_px': [250, 250, 500, 500] if reject else None, 'mask': None, 'ms': 120,
            'cost_usd': .001}


routes.API_KEY = 'e2e-configured'
routes.service.inspector = vision
routes.service.memory = HindsightMemory('https://memory.example', 'e2e-key', transport=httpx.MockTransport(respond))
uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('E2E_PORT', '8771')), log_level='warning')
