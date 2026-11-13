"""Read reject classes, clauses, size limits and part width out of a visual inspection specification.

The rule-based reader is free and deterministic, so every specification gets classes without a model call.
It looks for numbered clauses ("4.1 Hole: ...") under a REJECT heading. Specifications it cannot read fall back
to one generic "defect" class; the model-based reader in forge/spec.py can then be run on request.
"""
from __future__ import annotations

import io
import re

CLAUSE = re.compile(r'^\s*(\d+(?:\.\d+)+)\s+([A-Za-z][A-Za-z0-9 /&()\'-]{0,40}?)\s*[:–—-]\s*(.+)$')
SECTION = re.compile(r'^\s*\d+\.?\s+[A-Z][A-Za-z ()/-]*\s*$|^\s*\d+\.\s+[A-Z]')
MM = r'(\d+(?:\.\d+)?)\s*mm'
LIMIT = re.compile(rf'(?:(?:larger|longer|wider|deeper|greater|more|bigger)\s+than|over|exceed(?:s|ing)?|above|>|≥|>=)\s*{MM}',
                   re.IGNORECASE)
WIDTH = [re.compile(rf'(?:nominal\s+)?(?:width|diameter|size)\s*(?:of|is|=|:)?\s*{MM}', re.IGNORECASE),
         re.compile(rf'{MM}\s+(?:wide|in\s+width|in\s+diameter|diameter)', re.IGNORECASE)]
GENERIC = {'defect_type': 'defect', 'label': 'Defect', 'clause': '', 'description': 'Any reject condition in the specification.',
           'limit_mm': None}
MAX_CLASSES = 12


def slug(text: str) -> str:
    value = re.sub(r'[^a-z0-9]+', '_', text.casefold()).strip('_')
    return value[:24] or 'defect'


def limit_mm(text: str) -> float | None:
    match = LIMIT.search(text)
    return float(match.group(1)) if match else None


def part_width_mm(text: str) -> float | None:
    for pattern in WIDTH:
        if match := pattern.search(text):
            return float(match.group(1))
    return None


def part_name(text: str) -> str:
    for line in text.splitlines():
        if match := re.match(r'^\s*Part\s*:\s*(.+)$', line, re.IGNORECASE):
            return match.group(1).split(',')[0].strip()[:80]
    return ''


def parse_spec(text: str) -> dict:
    lines = text.splitlines()
    in_reject, seen_reject, classes = False, False, []
    for line in lines:
        if re.search(r'\bREJECT', line) and not CLAUSE.match(line):
            in_reject, seen_reject = True, True
            continue
        if in_reject and SECTION.match(line) and not CLAUSE.match(line):
            in_reject = False
        if not in_reject:
            continue
        if match := CLAUSE.match(line):
            clause, label, description = match.groups()
            classes.append({'defect_type': slug(label), 'label': label.strip(), 'clause': clause,
                            'description': description.strip()[:400], 'limit_mm': limit_mm(description)})
    unique, seen = [], set()
    for item in classes:
        if item['defect_type'] not in seen and item['defect_type'] != 'good':
            unique.append(item)
            seen.add(item['defect_type'])
    return {'part_name': part_name(text), 'part_width_mm': part_width_mm(text),
            'classes': unique[:MAX_CLASSES] or [dict(GENERIC)],
            'source': 'rules' if unique else 'fallback', 'found_reject_section': seen_reject}


def from_model(taxonomy: dict) -> dict:
    """Normalise the model reader's output to the same shape as parse_spec."""
    classes, seen = [], set()
    for d in taxonomy.get('defects', []):
        kind = slug(d.get('defect_type', ''))
        if kind in seen or kind == 'good':
            continue
        seen.add(kind)
        classes.append({'defect_type': kind, 'label': kind.replace('_', ' ').capitalize(), 'clause': d.get('clause', ''),
                        'description': d.get('description', '')[:400], 'limit_mm': limit_mm(d.get('severity_note', ''))})
    width = taxonomy.get('part_width_mm') or None
    return {'part_name': taxonomy.get('part_name', ''), 'part_width_mm': float(width) if width else None,
            'classes': classes[:MAX_CLASSES] or [dict(GENERIC)], 'source': 'model', 'found_reject_section': True}


def pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return '\n'.join(page.extract_text() or '' for page in reader.pages).strip()
