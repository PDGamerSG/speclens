"""Validated API for the SpecLens inspection workspace."""
from __future__ import annotations

import asyncio
import io
import json
import os
import re
import uuid
from pathlib import Path
from typing import Literal

import sqlalchemy as sa

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, Response, UploadFile
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator, model_validator
from sse_starlette.sse import EventSourceResponse

from ..config import API_KEY, BUDGET_USD, FIXTURES, VAR
from ..forge.spec import DEFAULT_SPEC
from ..forge.spec import taxonomy as taxonomy_model
from ..jobs.queue import JobQueue
from ..jobs.queue import mode as queue_mode
from ..jobs.runner import failure, make_runner
from ..media import media_from_env
from ..observability import request_id
from ..meta import ledger
from ..public import owner
from .dashboard import dashboard
from .memory import HindsightMemory
from .spec import from_model, pdf_text
from .service import WorkspaceService
from .store import Scope, Store, now

router = APIRouter(prefix='/api/workspace', tags=['SpecLens'])
DEFAULT_FACTORY = 'Bangalore Foods'
DEFAULT_PART = 'Whole hazelnut'
MAX_UPLOAD = 8 * 1024 * 1024
memory_url = os.environ.get('HINDSIGHT_BASE_URL', '').strip()
if not memory_url and os.environ.get('HINDSIGHT_API_KEY'):
    memory_url = 'https://api.hindsight.vectorize.io'
service = WorkspaceService(Store(), HindsightMemory(memory_url, os.environ.get('HINDSIGHT_API_KEY', '')),
                           media=media_from_env(VAR / 'workspace'))

SAMPLES = [
    {'id': 'natural-shell', 'name': 'Natural shell', 'detail': 'Good part · generated sample',
     'path': 'parts/hazelnut_gen_01.jpg', 'source_group': 'generated-hazelnut-01', 'expected_verdict': 'good'},
    {'id': 'white-print', 'name': 'White marking', 'detail': 'Print defect · generated sample',
     'path': 'speclens/white-print-01.png', 'source_group': 'generated-hazelnut-01', 'expected_verdict': 'defect'},
    {'id': 'fine-crack', 'name': 'Shell crack', 'detail': 'Crack defect · generated sample',
     'path': 'demo_run/samples/s001_composite.jpg', 'source_group': 'generated-hazelnut-02', 'expected_verdict': 'defect'},
    {'id': 'small-hole', 'name': 'Small hole', 'detail': 'Hole defect · generated sample',
     'path': 'demo_run/samples/s000_composite.jpg', 'source_group': 'generated-hazelnut-01', 'expected_verdict': 'defect'},
    {'id': 'second-print', 'name': 'Another marking', 'detail': 'Print defect · generated sample',
     'path': 'speclens/white-print-02.png', 'source_group': 'generated-hazelnut-02', 'expected_verdict': 'defect'},
    {'id': 'second-natural', 'name': 'Natural texture', 'detail': 'Good part · generated sample',
     'path': 'parts/hazelnut_gen_02.jpg', 'source_group': 'generated-hazelnut-02', 'expected_verdict': 'good'},
]


_INSPECTION_MEDIA = re.compile(r'^(insp-[A-Za-z0-9]{1,40})(?:_[a-f0-9]{12})?(?:\.jpg|_overlay\.jpg|_mask\.png)$')
_CORRECTION_MEDIA = re.compile(r'^(correction-[A-Za-z0-9]{1,40})_crop\.jpg$')


def media_owner(filename: str) -> dict | None:
    """The record a media file belongs to, so the photo route can check its owner. Unknown names match nothing."""
    if match := _INSPECTION_MEDIA.fullmatch(filename):
        item = service.store.inspection(match.group(1))
        return item if item and f'/files/workspace/{filename}' in {
            item.get('image_url'), item.get('mask_url'), item.get('overlay_url')} else None
    if match := _CORRECTION_MEDIA.fullmatch(filename):
        return service.store.correction(match.group(1))
    return None


def make_scope(factory: str, part_family: str, spec_text: str, owner_id: str = '', revision_id: str | None = None) -> Scope:
    if len(factory) > 100 or len(part_family) > 100 or len(spec_text) > 12000:
        raise HTTPException(422, 'Factory and part names are limited to 100 characters, and the specification to 12,000.')
    try:
        return Scope(factory, part_family, spec_text.strip() or DEFAULT_SPEC, owner_id, revision_id=revision_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


def pilot_permission(request: Request, *roles: str):
    from ..pilot.auth import current_identity, require_identity
    identity = current_identity(request)
    if identity is not None and roles:
        return require_identity(request, roles=roles)
    return identity


def request_scope(request: Request, factory: str, part_family: str, spec_text: str, revision_id: str = '') -> Scope:
    owner_id = owner(request)
    if revision_id:
        from ..pilot.auth import require_identity
        from ..pilot.store import PilotStore
        identity = require_identity(request)
        catalog = PilotStore(service.store.engine)
        revision = catalog.get(identity['team']['id'], revision_id, 'revision')
        product = catalog.get(owner_id, revision['product_id'], 'product')
        return make_scope(product['factory'], product['name'], revision['spec_text'], owner_id, revision_id)
    return make_scope(factory, part_family, spec_text, owner_id)


def capture_scope(request: Request, factory: str, part_family: str, spec_text: str, *,
                  revision_id: str, lot_id: str, station_id: str, physical_part_id: str,
                  capture_id: str, retake_of: str = '') -> tuple[Scope, dict | None]:
    identity = pilot_permission(request, 'admin', 'engineer', 'operator')
    if identity is None:
        if any((revision_id, lot_id, station_id, physical_part_id, capture_id, retake_of)):
            raise HTTPException(401, 'Sign in to capture parts in a factory workspace.')
        return make_scope(factory, part_family, spec_text, owner(request)), None
    if not all((revision_id, lot_id, station_id, physical_part_id.strip())):
        raise HTTPException(422, 'Choose an approved revision, station and open lot, and identify the physical part.')
    capture_id = capture_id or f'capture-{uuid.uuid4().hex}'
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', capture_id) or len(physical_part_id.strip()) > 100:
        raise HTTPException(422, 'Use a capture ID up to 64 letters/digits and a part ID up to 100 characters.')
    from ..pilot.store import PilotStore
    actor = {**identity['user'], 'role': identity['role']}
    context = PilotStore(service.store.engine).capture_context(identity['team']['id'], actor,
        revision_id=revision_id, lot_id=lot_id, station_id=station_id, physical_part_id=physical_part_id.strip(),
        capture_id=capture_id, retake_of=retake_of or None)
    context['owner_id'] = identity['team']['id']
    return make_scope(context['factory'], context['part_family'], context['spec_text'],
                      identity['team']['id'], revision_id), context


async def read_input(file: UploadFile | None, sample_id: str) -> tuple[bytes, str, dict]:
    if sample_id:
        sample = next((s for s in SAMPLES if s['id'] == sample_id), None)
        if sample is None:
            raise HTTPException(404, 'Sample part not found.')
        data, name = (FIXTURES / sample['path']).read_bytes(), f'{sample_id}.jpg'
        source = {'source_kind': 'synthetic_sample', 'source_group': sample['source_group'], 'sample_id': sample_id}
    elif file is not None:
        data, name = await file.read(MAX_UPLOAD + 1), Path(file.filename or 'part.jpg').name
        source = {'source_kind': 'upload', 'source_group': None, 'sample_id': None}
    else:
        raise HTTPException(422, 'Choose a sample or upload a part photo.')
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, 'Choose an image smaller than 8 MB.')
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise HTTPException(400, 'Upload a JPG, PNG or WebP still photo.')
            if getattr(image, 'is_animated', False):
                raise HTTPException(400, 'Use one still photo for each inspection. Animated images are not supported.')
            if image.width * image.height > 25_000_000:
                raise HTTPException(400, 'Choose a photo smaller than 25 megapixels.')
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(400, 'This file is not a readable image. Upload a JPG, PNG or WebP photo.') from None
    return data, name, source


def require_model():
    if not API_KEY:
        raise HTTPException(503, 'Live inspection needs MODEL_API_KEY on the server. Add the key to .env and restart.')


def run_operation(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except Exception as error:
        mapped = failure(error)
        if mapped is None:
            raise
        raise HTTPException(mapped.status_code, mapped.detail) from None


jobs = JobQueue(lambda: service.store.engine, make_runner(lambda: service))
WAIT_SECONDS = 110  # under the 120 s Vercel waits for an origin's first byte


def enqueue(kind: str, data: bytes, name: str, scope: Scope, source: dict, batch_id: str | None = None, **options) -> dict:
    """Store the photo where any worker can read it, then queue the job."""
    id = f'job-{uuid.uuid4().hex[:20]}'
    if kind == 'compare' and scope.owner_id.startswith('team-'):
        from ..pilot.integration import evaluation_policy
        options['policy'] = run_operation(evaluation_policy, service.store, scope)
    context = options.get('context')
    if context:
        import hashlib
        from ..pilot.integration import reserve_capture
        _, existing, context = run_operation(reserve_capture, service.store, scope, context, data,
                                             memory=options.get('use_memory', False))
        options['context'] = context
        id = 'job-' + hashlib.sha256(f'{scope.owner_id}:{context["capture_id"]}'.encode()).hexdigest()[:32]
        if existing is not None:
            return {'id': id, 'kind': kind, 'status': 'done', 'result': existing, 'batch_id': batch_id,
                    'attempts': 1, 'created_at': existing['created_at'], 'error': None}
        if (previous := jobs.get(id)) is not None:
            if previous['status'] == 'failed':
                return jobs.retry_failed(id, scope.owner_id)
            return previous
    upload = f'uploads/{id}'
    service.media.put(upload, data, 'application/octet-stream')
    payload = {'upload': upload, 'filename': name, 'source': source, 'request_id': request_id.get(), **options,
               'scope': {'factory': scope.factory, 'part_family': scope.part_family,
                         'spec_text': scope.spec_text, 'owner_id': scope.owner_id, 'revision_id': scope.revision_id}}
    try:
        return jobs.submit(kind, payload, scope.owner_id, batch_id=batch_id, id=id)
    except sa.exc.IntegrityError:
        if context and (previous := jobs.get(id)) is not None:
            return previous
        raise


async def finished(job: dict) -> dict:
    """Wait for a queued job and answer like the synchronous route always has."""
    done = job if job['status'] == 'done' else await jobs.wait(job['id'], WAIT_SECONDS)
    if done is None:
        raise HTTPException(404, 'Job not found.')
    if done['status'] == 'done':
        return done['result']
    if done['status'] == 'failed':
        raise HTTPException(done['error']['status_code'], done['error']['detail'])
    raise HTTPException(504, f'The inspection is still running. Check job {job["id"]} for the result.')


@router.get('/status')
def status():
    return {'ok': True, 'model_configured': bool(API_KEY), 'memory_configured': service.memory.configured,
            'model': 'muse-spark-1.3', 'spent_usd': ledger.spent(), 'budget_usd': BUDGET_USD,
            'cache': ledger.cache_stats(),
            'default_factory': DEFAULT_FACTORY, 'default_part': DEFAULT_PART, 'default_spec': DEFAULT_SPEC}


@router.get('/samples')
def samples():
    return {'samples': [{k: v for k, v in s.items() if k != 'path'} |
                        {'image_url': f'/files/fixtures/{s["path"]}'} for s in SAMPLES]}


@router.get('/overview')
def overview(request: Request, factory: str = DEFAULT_FACTORY, part_family: str = DEFAULT_PART, spec_text: str = '',
             limit: int = Query(100, ge=1, le=500), before: str = Query('', max_length=140),
             revision_id: str = Query('', max_length=64)):
    """One page of history, newest first. Records leave out the specification text, which the caller already has."""
    scope = request_scope(request, factory, part_family, spec_text, revision_id)
    store = service.store
    inspections = store.inspections(scope.id, limit=limit + 1, before=before or None, with_spec=False)
    has_more = len(inspections) > limit
    inspections = inspections[:limit]
    corrections = store.corrections(scope.id, with_spec=False)
    comparisons = store.comparisons(scope.id, limit=50, with_spec=False)
    return {'scope_id': scope.id, 'bank_id': scope.bank_id, 'spec_revision_id': scope.spec_revision_id,
            'taxonomy': scope_taxonomy(scope),
            'inspections': inspections, 'corrections': corrections, 'comparisons': comparisons,
            'has_more': has_more, 'next_before': f'{inspections[-1]["created_at"]}|{inspections[-1]["id"]}' if has_more else None,
            'stats': {'inspections': store.count_inspections(scope.id), 'corrections': len(corrections),
                      'comparisons': store.count_comparisons(scope.id),
                      'synced': sum(c['sync_status'] == 'synced' for c in corrections),
                      'pending': sum(c['sync_status'] != 'synced' for c in corrections)}}


@router.post('/inspect')
async def inspect_part(request: Request, file: UploadFile | None = File(None), sample_id: str = Form(''),
                       factory: str = Form(DEFAULT_FACTORY), part_family: str = Form(DEFAULT_PART),
                       spec_text: str = Form(''), memory_enabled: bool = Form(True),
                       revision_id: str = Form(''), lot_id: str = Form(''), station_id: str = Form(''),
                       physical_part_id: str = Form(''), capture_id: str = Form(''), retake_of: str = Form('')):
    data, name, source = await read_input(file, sample_id)
    require_model()
    scope, context = capture_scope(request, factory, part_family, spec_text, revision_id=revision_id, lot_id=lot_id,
        station_id=station_id, physical_part_id=physical_part_id, capture_id=capture_id, retake_of=retake_of)
    if context or queue_mode() == 'external':
        return await finished(await asyncio.to_thread(enqueue, 'inspect', data, name, scope, source,
                                                      use_memory=memory_enabled, context=context))
    return await asyncio.to_thread(run_operation, service.run, data, name, scope, use_memory=memory_enabled, **source)


class CorrectionIn(BaseModel):
    inspection_id: str = Field(min_length=1, max_length=80)
    verdict: Literal['good', 'defect']
    defect_type: str = Field(min_length=1, max_length=24, pattern=r'^[a-z0-9_]+$')
    rule_text: str = Field(min_length=10, max_length=2000)
    reviewer: str = Field(default='Quality engineer', min_length=1, max_length=80)

    @field_validator('rule_text', 'reviewer', mode='before')
    @classmethod
    def strip_text(cls, value):
        if not isinstance(value, str):
            return value
        if not value.strip():
            raise ValueError('Enter a quality standard and reviewer name.')
        return value.strip()

    @model_validator(mode='after')
    def matching_disposition(self):
        if (self.verdict == 'good') != (self.defect_type == 'good'):
            raise ValueError('An accepted part must use the good class; a rejected part must specify a defect class.')
        return self


@router.post('/corrections', status_code=201)
def correct(body: CorrectionIn, request: Request):
    identity = pilot_permission(request, 'admin', 'engineer')
    item = service.store.inspection(body.inspection_id)
    if item is None or item.get('owner_id', '') != owner(request):
        raise HTTPException(404, 'Inspection not found.')
    if body.defect_type != 'good' and body.defect_type not in service.correction_classes(item):
        raise HTTPException(422, 'Choose a defect class from this specification.')
    try:
        values = body.model_dump()
        if identity:
            values.update(reviewer=identity['user']['name'], actor={**identity['user'], 'role': identity['role']})
        return run_operation(service.correct, **values)
    except KeyError:
        raise HTTPException(404, 'Inspection not found.') from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@router.post('/corrections/{id}/sync')
def sync_correction(id: str, request: Request):
    pilot_permission(request, 'admin', 'engineer')
    item = service.store.correction(id)
    if item is None or item.get('owner_id', '') != owner(request):
        raise HTTPException(404, 'Correction not found.')
    try:
        return service.sync_correction(id)
    except KeyError:
        raise HTTPException(404, 'Correction not found.') from None


class ScopeIn(BaseModel):
    factory: str = Field(default=DEFAULT_FACTORY, min_length=1, max_length=100)
    part_family: str = Field(default=DEFAULT_PART, min_length=1, max_length=100)
    spec_text: str = Field(default='', max_length=12000)
    revision_id: str = Field(default='', max_length=64)

    def scope(self, owner_id: str = '') -> Scope:
        return make_scope(self.factory, self.part_family, self.spec_text, owner_id, self.revision_id or None)


@router.post('/recall')
def recall(body: ScopeIn, request: Request):
    scope = request_scope(request, body.factory, body.part_family, body.spec_text, body.revision_id)
    facts = run_operation(service.memory.recall, scope)
    from ..pilot.integration import eligible_sources
    sources = eligible_sources(service.store, scope)
    return {'bank_id': scope.bank_id, 'memories': [f for f in facts if f['source_id'] in sources]}


@router.post('/reflect')
def reflect(body: ScopeIn, request: Request):
    scope = request_scope(request, body.factory, body.part_family, body.spec_text, body.revision_id)
    if scope.owner_id.startswith('team-'):
        from ..pilot.integration import eligible_sources
        sources = eligible_sources(service.store, scope)
        return {'bank_id': scope.bank_id, 'summary': '\n'.join(c['rule_text'] for c in sources.values())
                or 'No approved, synchronized standards apply to this revision.'}
    return run_operation(service.memory.reflect, scope)


@router.post('/compare')
async def compare(request: Request, file: UploadFile | None = File(None), sample_id: str = Form(''),
                  factory: str = Form(DEFAULT_FACTORY), part_family: str = Form(DEFAULT_PART),
                  spec_text: str = Form(''), expected_verdict: Literal['good', 'defect', ''] = Form(''),
                  revision_id: str = Form('')):
    pilot_permission(request, 'admin', 'engineer')
    data, name, source = await read_input(file, sample_id)
    require_model()
    scope = request_scope(request, factory, part_family, spec_text, revision_id)
    if queue_mode() == 'external':
        return await finished(await asyncio.to_thread(enqueue, 'compare', data, name, scope, source,
                                                      expected_verdict=expected_verdict or None))
    return await asyncio.to_thread(run_operation, service.compare, data, name, scope,
                                   expected_verdict=expected_verdict or None, **source)


def own_job(id: str, request: Request) -> dict:
    job = jobs.get(id)
    if job is None or job['owner_id'] != owner(request):
        raise HTTPException(404, 'Job not found.')
    return job


@router.post('/jobs/inspect', status_code=202)
async def queue_inspection(request: Request, file: UploadFile | None = File(None), sample_id: str = Form(''),
                           factory: str = Form(DEFAULT_FACTORY), part_family: str = Form(DEFAULT_PART),
                           spec_text: str = Form(''), memory_enabled: bool = Form(True),
                           batch_id: str = Form('', pattern=r'^(batch-[a-f0-9]{8,32})?$'),
                           revision_id: str = Form(''), lot_id: str = Form(''), station_id: str = Form(''),
                           physical_part_id: str = Form(''), capture_id: str = Form(''), retake_of: str = Form('')):
    """Queue one inspection and return at once. Read the result from the job or its event stream.

    A batch is several of these requests sharing a batch_id, one photo each, so every request stays under the
    upload limit and counts once against the hourly limit."""
    data, name, source = await read_input(file, sample_id)
    require_model()
    scope, context = capture_scope(request, factory, part_family, spec_text, revision_id=revision_id, lot_id=lot_id,
        station_id=station_id, physical_part_id=physical_part_id, capture_id=capture_id, retake_of=retake_of)
    if batch_id and len(await asyncio.to_thread(jobs.batch, batch_id)) >= MAX_BATCH:
        raise HTTPException(413, f'A batch holds at most {MAX_BATCH} photos. Start another batch for the rest.')
    job = await asyncio.to_thread(enqueue, 'inspect', data, name, scope, source, batch_id=batch_id or None,
                                  use_memory=memory_enabled, context=context)
    return {**JobQueue.public(job), 'filename': name}


@router.post('/jobs/compare', status_code=202)
async def queue_comparison(request: Request, file: UploadFile | None = File(None), sample_id: str = Form(''),
                           factory: str = Form(DEFAULT_FACTORY), part_family: str = Form(DEFAULT_PART),
                           spec_text: str = Form(''), expected_verdict: Literal['good', 'defect', ''] = Form(''),
                           revision_id: str = Form('')):
    pilot_permission(request, 'admin', 'engineer')
    data, name, source = await read_input(file, sample_id)
    require_model()
    scope = request_scope(request, factory, part_family, spec_text, revision_id)
    job = await asyncio.to_thread(enqueue, 'compare', data, name, scope, source, expected_verdict=expected_verdict or None)
    return JobQueue.public(job)


MAX_BATCH = 50


@router.get('/batches/{batch_id}')
def get_batch(batch_id: str, request: Request):
    """Every job in one of this visitor's batches, with its result once finished."""
    items = [j for j in jobs.batch(batch_id) if j['owner_id'] == owner(request)]
    if not items:
        raise HTTPException(404, 'Batch not found.')
    counts = {status: sum(j['status'] == status for j in items) for status in ('queued', 'running', 'done', 'failed')}
    return {'batch_id': batch_id, 'counts': counts, 'finished': counts['queued'] + counts['running'] == 0,
            'jobs': [{**JobQueue.public(j), 'filename': j['payload'].get('filename')} for j in items]}


@router.get('/jobs/{id}')
def get_job(id: str, request: Request):
    return JobQueue.public(own_job(id, request))


@router.get('/jobs/{id}/events')
async def job_events(id: str, request: Request):
    """Server-sent events: one 'status' per change, then 'done' or 'failed'. A 15 s ping keeps proxies open."""
    await asyncio.to_thread(own_job, id, request)

    async def stream():
        last = None
        while True:
            try:
                job = await asyncio.to_thread(own_job, id, request)
            except HTTPException:
                return
            if job['status'] != last:
                last = job['status']
                if last in ('done', 'failed'):
                    yield {'event': last, 'data': json.dumps(JobQueue.public(job))}
                    return
                yield {'event': 'status', 'data': json.dumps({'id': id, 'status': last, 'attempts': job['attempts']})}
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.5)

    return EventSourceResponse(stream(), ping=15)


@router.get('/export')
def export_data(request: Request):
    """Every record this visitor stored, as one JSON download."""
    records = service.store.export_owner(owner(request))
    body = json.dumps({'format_version': 1, 'exported_at': now(), **records}, ensure_ascii=False)
    return Response(body, media_type='application/json',
                    headers={'Content-Disposition': 'attachment; filename="speclens-workspace-export.json"'})


class DeleteIn(BaseModel):
    confirm: Literal['DELETE']


@router.delete('/data')
def delete_data(body: DeleteIn, request: Request):
    """Delete this visitor's records, photos and Hindsight banks. The body must say DELETE, so it is never an accident."""
    pilot_permission(request, 'admin')
    try:
        return run_operation(service.delete_owner, owner(request))
    except ValueError as error:
        raise HTTPException(409, str(error)) from None


class SpecIn(BaseModel):
    spec_text: str = Field(min_length=1, max_length=12000)


@router.post('/specs/parse')
def parse_specification(body: SpecIn, request: Request):
    """Reject classes, clauses, limits and part width read by rules. No model call, so it is free to repeat."""
    return service.taxonomy(body.spec_text, owner(request))


MAX_SPEC_FILE = 4 * 1024 * 1024


@router.post('/specs/extract')
async def extract_specification(request: Request, file: UploadFile | None = File(None), spec_text: str = Form(''),
                                use_model: bool = Form(False)):
    """Read a specification from a PDF or text file, or from text. With use_model, the vision model reads the
    classes and the result is saved for every later inspection under this specification."""
    pilot_permission(request, 'admin', 'engineer')
    if file is not None:
        data = await file.read(MAX_SPEC_FILE + 1)
        if len(data) > MAX_SPEC_FILE:
            raise HTTPException(413, 'Choose a specification file smaller than 4 MB.')
        if data[:5] == b'%PDF-':
            try:
                spec_text = await asyncio.to_thread(pdf_text, data)
            except Exception:
                raise HTTPException(400, 'This PDF could not be read. Paste the specification text instead.') from None
        else:
            try:
                spec_text = data.decode('utf-8')
            except UnicodeDecodeError:
                raise HTTPException(400, 'Upload a PDF or a UTF-8 text file.') from None
    spec_text = spec_text.strip()
    if not spec_text:
        raise HTTPException(422, 'The specification is empty. A scanned PDF needs its text pasted in.')
    if len(spec_text) > 12000:
        raise HTTPException(422, f'The specification has {len(spec_text):,} characters. The limit is 12,000.')
    if use_model:
        require_model()
        reading = await asyncio.to_thread(run_operation, taxonomy_model, spec_text)
        return {'spec_text': spec_text, 'taxonomy': service.save_taxonomy(spec_text, from_model(reading), owner(request))}
    return {'spec_text': spec_text, 'taxonomy': service.taxonomy(spec_text, owner(request))}


@router.get('/dashboard')
def quality_dashboard(request: Request, factory: str = DEFAULT_FACTORY, part_family: str = DEFAULT_PART,
                      spec_text: str = '', days: int = Query(30, ge=1, le=365), revision_id: str = Query('', max_length=64)):
    """Reject rate, defect Pareto, corrections, memory use, cost and latency for this scope."""
    scope = request_scope(request, factory, part_family, spec_text, revision_id)
    return dashboard(service.store, scope.id, scope_taxonomy(scope)['classes'], days)


def scope_taxonomy(scope: Scope) -> dict:
    if scope.revision_id:
        from ..pilot.store import PilotStore
        return PilotStore(service.store.engine).get(scope.owner_id, scope.revision_id, 'revision')['taxonomy']
    return service.taxonomy(scope.spec_text, scope.owner_id)
