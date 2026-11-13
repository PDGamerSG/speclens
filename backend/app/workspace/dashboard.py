"""Quality dashboard for one scope: what a plant QA lead reads each morning.

Reads the real columns on inspections and corrections, never the JSON payloads of inspections, so it stays
fast as history grows. Cache use comes from the server-wide spend ledger.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import sqlalchemy as sa

from .. import db
from ..meta import ledger
from .store import Store


def percentile(values: list[int], share: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(share * (len(ordered) - 1))))]


def dashboard(store: Store, scope_id: str, classes: list[dict], days: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    i, k = db.inspections, db.corrections
    with store.engine.connect() as c:
        rows = c.execute(sa.select(i.c.created_at, i.c.verdict, i.c.defect_type, i.c.cost_usd, i.c.latency_ms,
                                   i.c.memory_enabled, i.c.cited_memories)
                         .where(i.c.scope_id == scope_id, i.c.created_at >= since.isoformat())).all()
        corrections = c.execute(sa.select(k.c.created_at, k.c.verdict, k.c.payload)
                                .where(k.c.scope_id == scope_id, k.c.created_at >= since.isoformat())).all()

    daily: dict[str, dict] = {}
    for offset in range(days, -1, -1):
        day = (since + timedelta(days=days - offset)).date().isoformat()
        daily[day] = {'day': day, 'inspections': 0, 'accepted': 0, 'rejected': 0, 'review': 0, 'cost_usd': 0.0}
    pareto: dict[str, int] = {}
    for row in rows:
        d = daily.setdefault(row.created_at[:10], {'day': row.created_at[:10], 'inspections': 0, 'accepted': 0,
                                                   'rejected': 0, 'review': 0, 'cost_usd': 0.0})
        d['inspections'] += 1
        d['cost_usd'] += row.cost_usd or 0
        if row.verdict == 'good':
            d['accepted'] += 1
        elif row.verdict == 'defect':
            d['rejected'] += 1
            pareto[row.defect_type or 'defect'] = pareto.get(row.defect_type or 'defect', 0) + 1
        else:
            d['review'] += 1

    weekly: dict[str, int] = {}
    overturned = 0
    for row in corrections:
        day = date.fromisoformat(row.created_at[:10])
        week = (day - timedelta(days=day.weekday())).isoformat()
        weekly[week] = weekly.get(week, 0) + 1
        overturned += row.payload.get('original_verdict') != row.verdict

    n = len(rows)
    rejected = sum(r.verdict == 'defect' for r in rows)
    review = sum(r.verdict not in ('good', 'defect') for r in rows)
    with_memory = [r for r in rows if r.memory_enabled]
    cost = sum(r.cost_usd or 0 for r in rows)
    latencies = [r.latency_ms for r in rows if r.latency_ms]
    labels = {c['defect_type']: c for c in classes}
    total_defects = sum(pareto.values())
    return {
        'days': days, 'since': since.isoformat(),
        'totals': {
            'inspections': n, 'accepted': n - rejected - review, 'rejected': rejected, 'review': review,
            'reject_rate': rejected / n if n else None, 'review_rate': review / n if n else None,
            'corrections': len(corrections), 'overturned': overturned,
            'corrected_share': len(corrections) / n if n else None,
            'memory_inspections': len(with_memory),
            'citation_rate': sum((r.cited_memories or 0) > 0 for r in with_memory) / len(with_memory) if with_memory else None,
            'cost_usd': round(cost, 4), 'cost_per_inspection': round(cost / n, 5) if n else None,
            'latency_p50_ms': percentile(latencies, 0.5), 'latency_p95_ms': percentile(latencies, 0.95)},
        'daily': [{**d, 'cost_usd': round(d['cost_usd'], 4)} for d in sorted(daily.values(), key=lambda d: d['day'])],
        'pareto': [{'defect_type': kind, 'label': labels.get(kind, {}).get('label', kind.replace('_', ' ').capitalize()),
                    'clause': labels.get(kind, {}).get('clause', ''), 'count': count,
                    'share': count / total_defects}
                   for kind, count in sorted(pareto.items(), key=lambda item: (-item[1], item[0]))],
        'corrections_weekly': [{'week': week, 'corrections': count} for week, count in sorted(weekly.items())],
        'cache': ledger.cache_stats(),
    }
