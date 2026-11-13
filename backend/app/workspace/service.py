"""Inspect, correct, remember and compare without mutating the base specification."""
from __future__ import annotations

import hashlib
import io
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

from ..forge.composite import overlay
from ..inspect.inspector import inspect
from ..inspect.measure import measure
from ..media import LocalMedia, MediaStore
from .memory import HindsightMemory, MemoryUnavailable
from .spec import parse_spec
from .store import Scope, Store, now, spec_revision_id


log = logging.getLogger('speclens.memory')
ALERT_AFTER = 5
TAXONOMY_TTL = 60  # seconds; a worker sees a newly saved model reading within a minute


def sync_backoff(attempts: int) -> float:
    """Seconds before the next memory sync attempt: 1 minute, doubling, at most 6 hours."""
    return min(60 * 2 ** max(attempts - 1, 0), 6 * 3600)


def jpeg(image: Image.Image, quality: int = 94) -> bytes:
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=quality)
    return out.getvalue()


class WorkspaceService:
    def __init__(self, store: Store, memory: HindsightMemory, *, inspector=None, media_root: Path | None = None,
                 media: MediaStore | None = None):
        if media is None and media_root is None:
            raise ValueError('Give the service a media store or a local media folder.')
        self.store = store
        self.memory = memory
        self.inspector = inspector or inspect
        self.media = media or LocalMedia(Path(media_root))
        self._taxonomies: dict[str, tuple[float, dict]] = {}
        self.masks = os.environ.get('SPECLENS_MASKS', '1') == '1'  # SAM 3.1 outline for each defect, $0.0025 each

    def run(self, data: bytes, filename: str, scope: Scope, *, use_memory: bool, source_kind: str = 'upload',
            source_group: str | None = None, sample_id: str | None = None) -> dict:
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
        taxonomy = self.taxonomy(scope.spec_text)
        classes = [c['defect_type'] for c in taxonomy['classes']]
        references, used = self.reference_crops(memories, sources)
        options = {'memory_exemplars': references} if references else {}
        result = self.inspector(image, scope.spec_text, classes, memory_context=memories,
                                with_mask=self.masks, require_mask=False, **options)
        mask = result.pop('mask', None)
        id = f'insp-{uuid.uuid4().hex[:16]}'
        self.media.put(f'{id}.jpg', jpeg(image), 'image/jpeg')
        extra = self.save_mask(id, image, mask, result, taxonomy) if mask is not None and mask.any() else {}
        item = {**result, **extra, 'id': id, 'scope_id': scope.id, 'factory': scope.factory,
                'owner_id': scope.owner_id,
                'part_family': scope.part_family, 'spec_text': scope.spec_text,
                'image_sha256': image_hash, 'filename': filename,
                'source_kind': source_kind, 'source_group': source_group, 'sample_id': sample_id,
                'image_url': f'/files/workspace/{id}.jpg', 'image_width': image.width, 'image_height': image.height,
                'memory_enabled': use_memory, 'memory_status': ('recalled' if memories else 'empty') if use_memory else 'disabled',
                'memories': memories, 'reference_crops': used, 'bank_id': scope.bank_id if use_memory else None,
                'created_at': now(), 'model': 'muse-spark-1.3'}
        return self.store.add_inspection(item)

    def save_mask(self, id: str, image: Image.Image, mask: np.ndarray, result: dict, taxonomy: dict) -> dict:
        """Store the mask and an outlined copy of the photo, and measure the defect against its clause."""
        if mask.shape != (image.height, image.width):
            mask = cv2.resize(mask.astype(np.uint8), image.size, interpolation=cv2.INTER_NEAREST).astype(bool)
        png = io.BytesIO()
        Image.fromarray(mask.astype(np.uint8) * 255).save(png, 'PNG')
        self.media.put(f'{id}_mask.png', png.getvalue(), 'image/png')
        outlined = Image.fromarray(overlay(np.array(image), mask, color=(207, 42, 30)))
        self.media.put(f'{id}_overlay.jpg', jpeg(outlined, 92), 'image/jpeg')
        clause = next((c for c in taxonomy['classes'] if c['defect_type'] == result.get('type')), None)
        measurement = measure(mask, result.get('part_box_px'), taxonomy.get('part_width_mm'),
                              clause['limit_mm'] if clause else None)
        extra = {'mask_url': f'/files/workspace/{id}_mask.png', 'overlay_url': f'/files/workspace/{id}_overlay.jpg',
                 'measurement': measurement}
        if measurement and measurement['within_limit'] and result['verdict'] == 'defect':
            # The clause rejects only above its size limit, so a smaller defect goes to a person, not to the scrap bin.
            result['verdict'] = 'uncertain'
            extra['size_note'] = (f'Measured {measurement["length_mm"]} mm, within the {measurement["limit_mm"]} mm limit '
                                  f'of clause {clause["clause"]}. Confirm before rejecting.')
        return extra

    def reference_crops(self, memories: list[dict], sources: dict, limit: int = 2) -> tuple[list, list[str]]:
        """Up to two defect crops saved with the recalled corrections, in a stable order so the prompt caches."""
        ids = sorted({m['source_id'] for m in memories if sources.get(m['source_id'], {}).get('crop_url')})
        references, used = [], []
        for cid in ids:
            data = self.media.get(f'{cid}_crop.jpg')
            if data is None:
                continue
            c = sources[cid]
            decision = 'reject' if c['verdict'] == 'defect' else 'accept'
            label = (f'Reference crop from correction {cid}: a quality engineer decided to {decision} this '
                     f'({c["defect_type"]}). Use it to compare with the part above.')
            references.append((label, Image.open(io.BytesIO(data)).convert('RGB')))
            used.append(cid)
            if len(used) == limit:
                break
        return references, used

    def crop(self, inspection: dict) -> bytes | None:
        """The defect region the engineer corrected, with context around it, at most 384 pixels on a side."""
        data = self.media.get(f'{inspection["id"]}.jpg')
        if data is None:
            return None
        with Image.open(io.BytesIO(data)) as photo:
            image = photo.convert('RGB')
        box = inspection.get('box_px')
        if box:
            x0, y0, x1, y1 = box
            pad = max(48, int(0.35 * max(x1 - x0, y1 - y0)))
            image = image.crop((max(0, x0 - pad), max(0, y0 - pad), min(image.width, x1 + pad), min(image.height, y1 + pad)))
        image.thumbnail((384, 384), Image.Resampling.LANCZOS)
        return jpeg(image, 90)

    def taxonomy(self, spec_text: str) -> dict:
        """Reject classes for a specification: the model's reading if one was saved, else the rule-based one."""
        sid = spec_revision_id(spec_text)
        cached = self._taxonomies.get(sid)
        if cached is None or time.monotonic() - cached[0] > TAXONOMY_TTL:
            cached = (time.monotonic(), self.store.taxonomy(sid) or parse_spec(spec_text))
            self._taxonomies[sid] = cached
        return cached[1]

    def save_taxonomy(self, spec_text: str, taxonomy: dict) -> dict:
        sid = self.store.save_taxonomy(spec_text, taxonomy)
        self._taxonomies[sid] = (time.monotonic(), taxonomy)
        return taxonomy

    def correction_classes(self, inspection: dict) -> set[str]:
        """Classes a correction of this inspection may use: the spec's classes, plus the class the model chose."""
        allowed = {c['defect_type'] for c in self.taxonomy(inspection['spec_text'])['classes']}
        return allowed | ({inspection['type']} - {'good'})

    def correct(self, inspection_id: str, **values) -> dict:
        inspection = self.store.inspection(inspection_id)
        if inspection is None:
            raise KeyError('Inspection not found.')
        id = f'correction-{uuid.uuid4().hex}'
        crop = self.crop(inspection) if inspection.get('image_url', '').startswith('/files/workspace/') else None
        extra = {}
        if crop:
            self.media.put(f'{id}_crop.jpg', crop, 'image/jpeg')
            extra['crop_url'] = f'/files/workspace/{id}_crop.jpg'
        try:
            correction = self.store.add_correction(inspection_id, id=id, **values, **extra)
        except Exception:
            if crop:
                self.media.delete(f'{id}_crop.jpg')
            raise
        return self.sync_correction(correction['id'])

    def sync_correction(self, id: str) -> dict:
        c = self.store.correction(id)
        if c is None:
            raise KeyError('Correction not found.')
        if c['sync_status'] == 'synced':
            return c
        scope = Scope(c['factory'], c['part_family'], c['spec_text'], c.get('owner_id', ''))
        try:
            self.memory.retain(scope, c)
        except MemoryUnavailable as exc:
            return self.store.mark_sync(id, 'pending', str(exc), retry_in=sync_backoff(self.store.sync_attempts(id)))
        return self.store.mark_sync(id, 'synced')

    def drain_outbox(self, limit: int = 20) -> dict:
        """Retry memory syncs that are due. The worker calls this every minute, so no correction waits on a click."""
        outcome = {'synced': 0, 'pending': 0}
        for id in self.store.due_corrections(limit):
            result = self.sync_correction(id)
            outcome['synced' if result['sync_status'] == 'synced' else 'pending'] += 1
            if result['sync_status'] != 'synced' and self.store.sync_attempts(id) >= ALERT_AFTER:
                log.error('Correction %s has failed to reach Hindsight %d times: %s',
                          id, self.store.sync_attempts(id), result.get('sync_error'))
        return outcome

    def compare(self, data: bytes, filename: str, scope: Scope, *, expected_verdict: str | None = None,
                source_kind: str = 'upload', source_group: str | None = None, sample_id: str | None = None) -> dict:
        # Alternate order across comparisons so the same arm is not always called first.
        id = f'compare-{uuid.uuid4().hex[:16]}'
        order = [False, True] if int(id[-1], 16) % 2 else [True, False]
        arms = {}
        for use_memory in order:
            arms[use_memory] = self.run(data, filename, scope, use_memory=use_memory,
                                        source_kind=source_kind, source_group=source_group, sample_id=sample_id)
        corrections = self.store.corrections(scope.id)
        reused_image = any(c['image_sha256'] == arms[False]['image_sha256'] for c in corrections)
        shared_source = bool(source_group) and any(c.get('source_group') == source_group for c in corrections)
        reuse_reason = 'reused_image' if reused_image else 'shared_source_photo' if shared_source else 'not_used_for_correction'
        result = {'id': id, 'scope_id': scope.id, 'created_at': now(),
                  'baseline': arms[False], 'with_memory': arms[True],
                  'expected_verdict': expected_verdict,
                  'changed': arms[False]['verdict'] != arms[True]['verdict'],
                  'held_out': not reused_image and not shared_source, 'reuse_reason': reuse_reason,
                  'note': 'One paired inspection. Model outputs can vary; this is not an accuracy benchmark.'}
        return self.store.add_comparison(result)

    # Retention and deletion --------------------------------------------------------------------------------

    def _clean_up(self, removed: dict, *, drop_banks: bool, delete_memory: bool = True) -> dict:
        """Remove the media and Hindsight memory of deleted records. Failures are counted, not hidden."""
        failed_media = 0
        for key in removed['media']:
            try:
                self.media.delete(key)
            except Exception:
                failed_media += 1
                log.exception('Could not delete media %s', key)
        failed_memory = 0
        if self.memory.configured and delete_memory:
            targets = ([(f'speclens-{s}', None) for s in removed['scope_ids']] if drop_banks else removed['memories'])
            for bank, document in targets:
                try:
                    self.memory.drop_bank(bank) if document is None else self.memory.forget(bank, document)
                except MemoryUnavailable:
                    failed_memory += 1
                    log.error('Could not delete Hindsight memory %s %s', bank, document or '')
        summary = {k: removed[k] for k in ('inspections', 'corrections', 'comparisons', 'jobs')}
        return {**summary, 'media_files': len(removed['media']) - failed_media, 'media_failed': failed_media,
                'memory_failed': failed_memory}

    def delete_owner(self, owner_id: str) -> dict:
        """Everything one visitor stored: records, photos and their Hindsight banks."""
        if self.store.has_active_jobs(owner_id):
            raise ValueError('Wait for your queued and running inspections to finish before deleting your data.')
        records = self.store.export_owner(owner_id)
        scopes = {item['scope_id'] for items in records.values() for item in items}
        # Keep local records and their bank IDs until remote deletion succeeds, so a failed request is retryable.
        if self.memory.configured:
            for scope_id in sorted(scopes):
                self.memory.drop_bank(f'speclens-{scope_id}')
        return self._clean_up(self.store.delete_owner(owner_id), drop_banks=True, delete_memory=False)

    def purge(self, retention_days: int, job_days: int = 7) -> dict:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        removed = self.store.purge_before(cutoff, time.time() - job_days * 86400)
        return self._clean_up(removed, drop_banks=False)
