"""One part-resolution policy for lot closure and evidence reports."""
from __future__ import annotations

from collections import defaultdict


def lot_resolution(captures: list[dict], reviews: list[dict], inspections: dict[str, dict]) -> dict:
    by_id = {item['id']: item for item in captures}

    def replaced(record):
        target = by_id.get(record.get('resolved_by'))
        if (not target or target.get('status') != 'done' or not target.get('inspection_id')
                or target.get('lot_id') != record.get('lot_id')
                or target.get('physical_part_id') != record.get('physical_part_id')
                or target.get('revision_id') != record.get('revision_id')
                or target.get('retake_of') != record.get('capture_id', record['id'])):
            return False
        context = (inspections.get(target['inspection_id'], {}).get('pilot') or {})
        return (context.get('capture_id') == target['id']
                and context.get('lot_id') == record.get('lot_id') and not context.get('quarantined'))

    pending_captures = {item['id'] for item in captures if item.get('status') != 'done' and not (
        item.get('status') in {'failed', 'quarantined'} and replaced(item))}
    pending_reviews = set()
    for item in reviews:
        if item.get('status') != 'closed':
            pending_reviews.add(item['id'])
        elif item.get('quarantined'):
            if item.get('outcome') not in {'reject', 'retake'} or not replaced(item):
                pending_reviews.add(item['id'])
        elif item.get('outcome') in {'hold', 'retake'} and not replaced(item):
            pending_reviews.add(item['id'])

    captures_by_part, reviews_by_part = defaultdict(list), defaultdict(list)
    part_key = lambda item: item.get('physical_part_id') or item.get('capture_id') or item['id']
    order = lambda item: (item['created_at'], item['id'])
    for item in captures:
        captures_by_part[part_key(item)].append(item)
    for item in reviews:
        reviews_by_part[part_key(item)].append(item)
    parts = []
    for part in sorted(captures_by_part.keys() | reviews_by_part.keys()):
        attempts, decisions = captures_by_part[part], reviews_by_part[part]
        latest_capture = max(attempts, key=order) if attempts else None
        eligible = [r for r in decisions if r.get('capture_id') == latest_capture['id']] if latest_capture else decisions
        latest_review = max(eligible, key=order) if eligible else None
        capture_ids = [c['id'] for c in attempts if c['id'] in pending_captures]
        review_ids = [r['id'] for r in decisions if r['id'] in pending_reviews]
        final = bool(latest_review and latest_review.get('status') == 'closed'
                     and latest_review.get('outcome') in {'accept', 'reject'} and not latest_review.get('quarantined'))
        parts.append({'physical_part_id': part, 'latest_capture_id': latest_capture['id'] if latest_capture else None,
                      'latest_review_id': latest_review['id'] if latest_review else None,
                      'pending_capture_ids': sorted(capture_ids), 'pending_review_ids': sorted(review_ids),
                      'unresolved': bool(capture_ids or review_ids or not final)})
    return {'parts': parts, 'unresolved_parts': sum(p['unresolved'] for p in parts),
            'pending_capture_ids': sorted(pending_captures), 'pending_review_ids': sorted(pending_reviews)}
