"""Validated API for the SpecLens inspection workspace."""
from __future__ import annotations

import asyncio
import io
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from openai import APIError
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator, model_validator

from ..config import API_KEY, BUDGET_USD, FIXTURES, VAR
from ..forge.spec import DEFAULT_SPEC
from ..meta import ledger
from ..meta.client import MetaAPIError
from ..public import owner
from .memory import HindsightMemory, MemoryUnavailable
from .service import WorkspaceService
from .store import Scope, Store

router = APIRouter(prefix='/api/workspace', tags=['SpecLens'])
DEFAULT_FACTORY = 'Bangalore Foods'
DEFAULT_PART = 'Whole hazelnut'
MAX_UPLOAD = 8 * 1024 * 1024
memory_url = os.environ.get('HINDSIGHT_BASE_URL', '').strip()
if not memory_url and os.environ.get('HINDSIGHT_API_KEY'):
    memory_url = 'https://api.hindsight.vectorize.io'
service = WorkspaceService(Store(VAR / 'speclens.sqlite3'),
    HindsightMemory(memory_url, os.environ.get('HINDSIGHT_API_KEY', '')), media_root=VAR / 'workspace')

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


def make_scope(factory: str, part_family: str, spec_text: str, owner_id: str = '') -> Scope:
    if len(factory) > 100 or len(part_family) > 100 or len(spec_text) > 12000:
        raise HTTPException(422, 'Factory and part names are limited to 100 characters, and the specification to 12,000.')
    try:
        return Scope(factory, part_family, spec_text.strip() or DEFAULT_SPEC, owner_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


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
    except MemoryUnavailable as e:
        raise HTTPException(503, str(e)) from None
    except ledger.BudgetExceeded as e:
        raise HTTPException(402, str(e)) from None
    except (APIError, MetaAPIError):
        raise HTTPException(502, 'The vision model could not complete this inspection. Check the model connection and try again.') from None


@router.get('/status')
def status():
    return {'ok': True, 'model_configured': bool(API_KEY), 'memory_configured': service.memory.configured,
            'model': 'muse-spark-1.3', 'spent_usd': ledger.spent(), 'budget_usd': BUDGET_USD,
            'default_factory': DEFAULT_FACTORY, 'default_part': DEFAULT_PART, 'default_spec': DEFAULT_SPEC}


@router.get('/samples')
def samples():
    return {'samples': [{k: v for k, v in s.items() if k != 'path'} |
                        {'image_url': f'/files/fixtures/{s["path"]}'} for s in SAMPLES]}


@router.get('/overview')
def overview(request: Request, factory: str = DEFAULT_FACTORY, part_family: str = DEFAULT_PART, spec_text: str = ''):
    scope = make_scope(factory, part_family, spec_text, owner(request))
    inspections = service.store.inspections(scope.id)
    corrections = service.store.corrections(scope.id)
    comparisons = service.store.comparisons(scope.id)
    with service.store.connection() as db:
        total = db.execute('SELECT COUNT(*) FROM inspections WHERE scope_id=?', (scope.id,)).fetchone()[0]
    return {'scope_id': scope.id, 'bank_id': scope.bank_id, 'inspections': inspections,
            'corrections': corrections, 'comparisons': comparisons,
            'stats': {'inspections': total, 'corrections': len(corrections),
                      'synced': sum(c['sync_status'] == 'synced' for c in corrections),
                      'pending': sum(c['sync_status'] != 'synced' for c in corrections)}}


@router.post('/inspect')
async def inspect_part(request: Request, file: UploadFile | None = File(None), sample_id: str = Form(''),
                       factory: str = Form(DEFAULT_FACTORY), part_family: str = Form(DEFAULT_PART),
                       spec_text: str = Form(''), memory_enabled: bool = Form(True)):
    data, name, source = await read_input(file, sample_id)
    require_model()
    scope = make_scope(factory, part_family, spec_text, owner(request))
    return await asyncio.to_thread(run_operation, service.run, data, name, scope, use_memory=memory_enabled, **source)


class CorrectionIn(BaseModel):
    inspection_id: str = Field(min_length=1, max_length=80)
    verdict: Literal['good', 'defect']
    defect_type: Literal['good', 'hole', 'crack', 'cut', 'print']
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
    item = service.store.inspection(body.inspection_id)
    if item is None or item.get('owner_id', '') != owner(request):
        raise HTTPException(404, 'Inspection not found.')
    try:
        return service.correct(**body.model_dump())
    except KeyError:
        raise HTTPException(404, 'Inspection not found.') from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@router.post('/corrections/{id}/sync')
def sync_correction(id: str, request: Request):
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

    def scope(self, owner_id: str = '') -> Scope:
        return make_scope(self.factory, self.part_family, self.spec_text, owner_id)


@router.post('/recall')
def recall(body: ScopeIn, request: Request):
    scope = body.scope(owner(request))
    facts = run_operation(service.memory.recall, scope)
    sources = {c['id']: c for c in service.store.corrections(scope.id) if c['sync_status'] == 'synced'}
    return {'bank_id': scope.bank_id, 'memories': [f for f in facts if f['source_id'] in sources]}


@router.post('/reflect')
def reflect(body: ScopeIn, request: Request):
    return run_operation(service.memory.reflect, body.scope(owner(request)))


@router.post('/compare')
async def compare(request: Request, file: UploadFile | None = File(None), sample_id: str = Form(''),
                  factory: str = Form(DEFAULT_FACTORY), part_family: str = Form(DEFAULT_PART),
                  spec_text: str = Form(''), expected_verdict: Literal['good', 'defect', ''] = Form('')):
    data, name, source = await read_input(file, sample_id)
    require_model()
    return await asyncio.to_thread(run_operation, service.compare, data, name,
        make_scope(factory, part_family, spec_text, owner(request)), expected_verdict=expected_verdict or None, **source)
