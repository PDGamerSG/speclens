"""Inspect, correct, remember and compare without mutating the base specification."""
from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from ..inspect.inspector import inspect
from .memory import HindsightMemory, MemoryUnavailable
from .store import Scope, Store, now


class WorkspaceService:
    def __init__(self, store: Store, memory: HindsightMemory, *, inspector=None, media_root: Path):
        self.store = store
        self.memory = memory
        self.inspector = inspector or inspect
        self.media_root = Path(media_root)
        self.media_root.mkdir(parents=True, exist_ok=True)

    def run(self, data: bytes, filename: str, scope: Scope, *, use_memory: bool) -> dict:
        # Fail a required recall visibly; never label a baseline result as memory-enabled.
        facts = self.memory.recall(scope) if use_memory else []
        sources = {c['id']: c for c in self.store.corrections(scope.id) if c['sync_status'] == 'synced'}
        memories = [{**f, 'reviewer': sources[f['source_id']]['reviewer'],
                     'rule_text': sources[f['source_id']]['rule_text'],
                     'source_inspection_id': sources[f['source_id']]['inspection_id']}
                    for f in facts if f['source_id'] in sources]
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source).convert('RGB')
        # Metadata and filename changes do not create a new inspection image.
        # Hash canonical pixels before resizing; this does not detect near-duplicates.
        image_hash = hashlib.sha256(f'RGB:{image.width}x{image.height}:'.encode() + image.tobytes()).hexdigest()
        image.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        result = self.inspector(image, scope.spec_text, ['hole', 'crack', 'cut', 'print'],
                                memory_context=memories, with_mask=False)
        result.pop('mask', None)
        id = f'insp-{uuid.uuid4().hex[:16]}'
        image.save(self.media_root / f'{id}.jpg', 'JPEG', quality=94)
        item = {**result, 'id': id, 'scope_id': scope.id, 'factory': scope.factory,
                'part_family': scope.part_family, 'spec_text': scope.spec_text,
                'image_sha256': image_hash, 'filename': filename,
                'image_url': f'/files/workspace/{id}.jpg', 'image_width': image.width, 'image_height': image.height,
                'memory_enabled': use_memory, 'memory_status': ('recalled' if memories else 'empty') if use_memory else 'disabled',
                'memories': memories, 'bank_id': scope.bank_id if use_memory else None,
                'created_at': now(), 'model': 'muse-spark-1.3'}
        return self.store.add_inspection(item)

    def correct(self, inspection_id: str, **values) -> dict:
        correction = self.store.add_correction(inspection_id, **values)
        return self.sync_correction(correction['id'])

    def sync_correction(self, id: str) -> dict:
        c = self.store.correction(id)
        if c is None:
            raise KeyError('Correction not found.')
        if c['sync_status'] == 'synced':
            return c
        scope = Scope(c['factory'], c['part_family'], c['spec_text'])
        try:
            self.memory.retain(scope, c)
        except MemoryUnavailable as exc:
            return self.store.mark_sync(id, 'pending', str(exc))
        return self.store.mark_sync(id, 'synced')

    def compare(self, data: bytes, filename: str, scope: Scope, *, expected_verdict: str | None = None) -> dict:
        # Alternate order across comparisons so the same arm is not always called first.
        id = f'compare-{uuid.uuid4().hex[:16]}'
        order = [False, True] if int(id[-1], 16) % 2 else [True, False]
        arms = {}
        for use_memory in order:
            arms[use_memory] = self.run(data, filename, scope, use_memory=use_memory)
        result = {'id': id, 'scope_id': scope.id, 'created_at': now(),
                  'baseline': arms[False], 'with_memory': arms[True],
                  'expected_verdict': expected_verdict,
                  'changed': arms[False]['verdict'] != arms[True]['verdict'],
                  'held_out': not any(c['image_sha256'] == arms[False]['image_sha256'] for c in self.store.corrections(scope.id)),
                  'note': 'One paired inspection. Model outputs can vary; this is not an accuracy benchmark.'}
        return self.store.add_comparison(result)
