"""Factory overview: the figures a plant quality lead reads at the start of a shift.

Everything is derived from the team's own records. Human review outcomes are the decisions; the model's
recommendation is compared with them, never substituted for them.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from .resolution import lot_resolution
from .store import PilotStore

SEVERITY_RANK = {'critical': 0, 'major': 1, 'minor': 2}
DECIDED = ('accept', 'reject')


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _rate(count: int, denominator: int) -> dict:
    return {'count': count, 'denominator': denominator, 'rate': round(count / denominator, 4) if denominator else None}


def _hours(since: datetime | None, current: datetime) -> float | None:
    return round((current - since).total_seconds() / 3600, 1) if since else None


def insights(pilot: PilotStore, workspace, owner: str, days: int = 30) -> dict:
    current = datetime.now(timezone.utc)
    since = current - timedelta(days=days)
    products = {p['id']: p for p in pilot.list(owner, 'product')}
    revisions = {r['id']: r for r in pilot.list(owner, 'revision')}
    lots = {lot['id']: lot for lot in pilot.list(owner, 'lot')}
    captures = pilot.list(owner, 'capture')
    reviews = pilot.list(owner, 'review')
    standards = pilot.list(owner, 'standard')
    issues = pilot.list(owner, 'nonconformance')
    stations = pilot.list(owner, 'station')

    def product_of(lot_id: str) -> dict | None:
        lot = lots.get(lot_id)
        revision = revisions.get(lot['revision_id']) if lot else None
        return products.get(revision['product_id']) if revision else None

    review_by_inspection = {r['inspection_id']: r for r in reviews if r.get('inspection_id')}
    in_window = [c for c in captures if (_time(c['created_at']) or current) >= since]

    # Daily series: one bar per capture, coloured by its human review outcome.
    daily = {}
    for offset in range(days, -1, -1):
        day = (current - timedelta(days=offset)).date().isoformat()
        daily[day] = {'day': day, 'captures': 0, 'accept': 0, 'reject': 0, 'hold': 0, 'retake': 0, 'open': 0}
    for capture in in_window:
        day = capture['created_at'][:10]
        if day not in daily:
            continue
        review = review_by_inspection.get(capture.get('inspection_id'))
        bucket = review['outcome'] if review and review.get('status') == 'closed' and review.get('outcome') in daily[day] else 'open'
        daily[day]['captures'] += 1
        daily[day][bucket] += 1

    # Physical parts: a part passes first time when its first capture's review accepted it.
    parts = defaultdict(list)
    for capture in in_window:
        parts[(capture['lot_id'], capture['physical_part_id'])].append(capture)
    first_pass, decided_parts = 0, 0
    product_rows = {pid: {'product_id': pid, 'code': p.get('code', ''), 'name': p.get('name', pid), 'parts': 0,
                          'captures': 0, 'accept': 0, 'reject': 0, 'hold': 0, 'retake': 0, 'open': 0,
                          'first_pass': 0, 'decided': 0, 'open_issues': 0} for pid, p in products.items()}
    for (lot_id, _), attempts in parts.items():
        attempts.sort(key=lambda c: c['created_at'])
        product = product_of(lot_id)
        row = product_rows.get(product['id']) if product else None
        outcomes = [review_by_inspection.get(c.get('inspection_id')) for c in attempts]
        final = next((r for r in reversed(outcomes) if r and r.get('status') == 'closed'
                      and r.get('outcome') in ('accept', 'reject', 'hold')), None)
        first = outcomes[0]
        passed = bool(first and first.get('status') == 'closed' and first.get('outcome') == 'accept')
        if final and final.get('outcome') in DECIDED:
            decided_parts += 1
            first_pass += passed
        if row is not None:
            row['parts'] += 1
            row['captures'] += len(attempts)
            if final and final.get('outcome') in DECIDED:
                row['decided'] += 1
                row['first_pass'] += passed
            for review in outcomes:
                key = review['outcome'] if review and review.get('status') == 'closed' and review.get('outcome') in row else 'open'
                row[key] += 1

    # Model recommendation against the human decision, for closed accept/reject reviews.
    agreement, compared, model_review = 0, 0, 0
    defects = Counter()
    confirmed = Counter()
    labels = {}
    for review in reviews:
        if (_time(review['created_at']) or current) < since:
            continue
        inspection = review.get('inspection') or {}
        verdict = inspection.get('verdict')
        kind = inspection.get('type')
        if verdict == 'uncertain':
            model_review += 1
        if verdict == 'defect' and kind and kind != 'good':
            defects[kind] += 1
            if review.get('status') == 'closed' and review.get('outcome') == 'reject':
                confirmed[kind] += 1
            revision = revisions.get(review.get('revision_id'))
            for item in (revision or {}).get('taxonomy', {}).get('classes', []):
                labels.setdefault(item['defect_type'], (item.get('label') or kind, item.get('clause', '')))
        if review.get('status') == 'closed' and review.get('outcome') in DECIDED and verdict in ('good', 'defect'):
            compared += 1
            agreement += (review['outcome'] == 'accept') == (verdict == 'good')

    open_reviews = [r for r in reviews if r.get('status') != 'closed']
    oldest = min((_time(r['created_at']) for r in open_reviews if _time(r['created_at'])), default=None)
    open_issues = [i for i in issues if i.get('status') != 'closed']
    for issue in open_issues:
        product = product_of(issue.get('lot_id', ''))
        if product and product['id'] in product_rows:
            product_rows[product['id']]['open_issues'] += 1

    # Open lots: what still blocks closing each one.
    open_lots = []
    for lot in lots.values():
        if lot.get('status') != 'open':
            continue
        attempts = [c for c in captures if c['lot_id'] == lot['id']]
        lot_reviews = [r for r in reviews if r['lot_id'] == lot['id']]
        inspections = {c['inspection_id']: workspace.inspection(c['inspection_id'])
                       for c in attempts if c.get('inspection_id')}
        resolution = lot_resolution(attempts, lot_reviews, inspections)
        blocking = len(resolution['pending_capture_ids']) + len(resolution['pending_review_ids']) + resolution['unresolved_parts']
        product = product_of(lot['id'])
        open_lots.append({'id': lot['id'], 'reference': lot.get('reference', lot['id']),
                          'product': product.get('name') if product else '', 'captures': len(attempts),
                          'pending_reviews': len(resolution['pending_review_ids']),
                          'unresolved_parts': resolution['unresolved_parts'], 'ready_to_close': blocking == 0 and bool(attempts),
                          'opened_at': lot['created_at']})
    open_lots.sort(key=lambda item: item['opened_at'])

    attention = []
    for review in reviews:
        if review.get('quarantined') and review.get('status') != 'closed':
            attention.append({'kind': 'quarantine', 'id': review['id'], 'section': 'review', 'priority': 0,
                              'title': f'Quarantined result for {review.get("physical_part_id", "a part")}',
                              'detail': review.get('quarantine_reason') or 'Its recipe changed during inspection. Take a new capture.',
                              'age_hours': _hours(_time(review['created_at']), current)})
    for issue in open_issues:
        if issue.get('severity') in ('critical', 'major'):
            attention.append({'kind': 'issue', 'id': issue['id'], 'section': 'issues', 'priority': 1 + SEVERITY_RANK[issue['severity']],
                              'title': issue.get('title', 'Quality issue'), 'severity': issue['severity'],
                              'detail': f'{issue["severity"].capitalize()} issue, {issue.get("status", "open")}.',
                              'age_hours': _hours(_time(issue['created_at']), current)})
    for review in sorted(open_reviews, key=lambda r: r['created_at'])[:6]:
        if review.get('quarantined'):
            continue
        age = _hours(_time(review['created_at']), current)
        attention.append({'kind': 'review', 'id': review['id'], 'section': 'review', 'priority': 3 if (age or 0) >= 24 else 4,
                          'title': f'Review {review.get("physical_part_id", "a part")}',
                          'detail': 'Claimed and waiting for a decision.' if review.get('status') == 'claimed' else 'Waiting for a reviewer.',
                          'age_hours': age})
    for standard in standards:
        if standard.get('status') == 'candidate':
            attention.append({'kind': 'standard', 'id': standard['id'], 'section': 'standards', 'priority': 5,
                              'title': f'Approve or retire a proposed {standard.get("defect_type", "")} standard'.replace('  ', ' '),
                              'detail': standard.get('rule_text', '')[:140], 'age_hours': _hours(_time(standard['created_at']), current)})
    for lot in open_lots:
        if lot['ready_to_close']:
            attention.append({'kind': 'lot', 'id': lot['id'], 'section': 'lots', 'priority': 6,
                              'title': f'Close lot {lot["reference"]}', 'detail': 'Every part has a decision.',
                              'age_hours': _hours(_time(lot['opened_at']), current)})
    attention.sort(key=lambda item: (item['priority'], -(item['age_hours'] or 0)))
    # A few of each kind, so twelve open issues cannot hide a waiting review or a lot ready to close.
    caps, taken, varied = {'quarantine': 3, 'issue': 3, 'review': 3, 'standard': 2, 'lot': 2}, Counter(), []
    for item in attention:
        if taken[item['kind']] < caps[item['kind']]:
            varied.append(item)
            taken[item['kind']] += 1
    attention = varied

    window_reviews = [r for r in reviews if (_time(r['created_at']) or current) >= since]
    closed = [r for r in window_reviews if r.get('status') == 'closed']
    outcomes = Counter(r.get('outcome') for r in closed)
    product_list = []
    for row in product_rows.values():
        row['first_pass_yield'] = _rate(row['first_pass'], row['decided'])
        product_list.append(row)
    product_list.sort(key=lambda row: (-row['captures'], row['name']))
    return {
        'days': days, 'generated_at': current.isoformat(),
        'kpis': {
            'captures': len(in_window), 'parts': len(parts),
            'first_pass_yield': _rate(first_pass, decided_parts),
            'human_reject_rate': _rate(outcomes['reject'], len(closed)),
            'hold_rate': _rate(outcomes['hold'], len(closed)),
            'model_agreement': _rate(agreement, compared),
            'model_review_rate': _rate(model_review, len(window_reviews)),
            'open_reviews': len(open_reviews), 'oldest_open_review_hours': _hours(oldest, current),
            'open_lots': len(open_lots), 'closed_lots': sum(lot.get('status') == 'closed' for lot in lots.values()),
            'open_issues': len(open_issues), 'critical_open_issues': sum(i.get('severity') == 'critical' for i in open_issues),
            'candidate_standards': sum(s.get('status') == 'candidate' for s in standards),
            'approved_standards': sum(s.get('status') == 'approved' for s in standards),
            'active_stations': sum(bool(s.get('active')) for s in stations), 'products': len(products)},
        'daily': list(daily.values()),
        'products': product_list,
        'defects': [{'defect_type': kind, 'label': labels.get(kind, (kind.replace('_', ' ').capitalize(), ''))[0],
                     'clause': labels.get(kind, ('', ''))[1], 'flagged': count, 'confirmed': confirmed[kind]}
                    for kind, count in defects.most_common(8)],
        'issues': {'by_severity': dict(Counter(i.get('severity') for i in open_issues)),
                   'by_status': dict(Counter(i.get('status') for i in issues))},
        'open_lots': open_lots[:8],
        'attention': attention[:10],
    }
