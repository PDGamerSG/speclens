"""Benchmark statistics: detection metrics and paired bootstrap intervals for memory off against memory on.

A part counts as flagged when the decision is Reject or Review, because either way it does not pass unchecked.
"""
from __future__ import annotations

import random

FLAGGED = ('defect', 'uncertain')


def binary_metrics(rows: list[dict]) -> dict:
    """rows: {'expected': 'good'|'defect', 'verdict': 'good'|'defect'|'uncertain', 'type'?, 'expected_type'?}"""
    tp = sum(r['expected'] == 'defect' and r['verdict'] in FLAGGED for r in rows)
    fn = sum(r['expected'] == 'defect' and r['verdict'] not in FLAGGED for r in rows)
    fp = sum(r['expected'] == 'good' and r['verdict'] in FLAGGED for r in rows)
    tn = sum(r['expected'] == 'good' and r['verdict'] not in FLAGGED for r in rows)
    n = len(rows)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    if precision is None or recall is None:
        f1 = None
    else:
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    typed = [r for r in rows if r['expected'] == 'defect' and r['verdict'] == 'defect' and r.get('expected_type')]
    return {'n': n, 'tp': tp, 'fp': fp, 'tn': tn, 'fn': fn,
            'accuracy': (tp + tn) / n if n else None, 'precision': precision, 'recall': recall, 'f1': f1,
            'review_rate': sum(r['verdict'] == 'uncertain' for r in rows) / n if n else None,
            'class_accuracy': sum(r.get('type') == r['expected_type'] for r in typed) / len(typed) if typed else None}


def correct(row: dict) -> bool:
    return (row['verdict'] in FLAGGED) == (row['expected'] == 'defect')


def paired_bootstrap(baseline: list[dict], memory: list[dict], *, samples: int = 4000, seed: int = 7) -> dict:
    """95% intervals for accuracy with memory off, on, and their difference, resampling cases with their pair."""
    if len(baseline) != len(memory) or not baseline:
        raise ValueError('Both arms need the same, non-empty list of cases.')
    pairs = [(correct(a), correct(b)) for a, b in zip(baseline, memory)]
    rng = random.Random(seed)
    n = len(pairs)
    off, on, lift = [], [], []
    for _ in range(samples):
        draw = [pairs[rng.randrange(n)] for _ in range(n)]
        a = sum(x for x, _ in draw) / n
        b = sum(y for _, y in draw) / n
        off.append(a)
        on.append(b)
        lift.append(b - a)

    def interval(values: list[float]) -> list[float]:
        values = sorted(values)
        return [round(values[int(0.025 * (len(values) - 1))], 4), round(values[int(0.975 * (len(values) - 1))], 4)]

    point_off = sum(x for x, _ in pairs) / n
    point_on = sum(y for _, y in pairs) / n
    return {'cases': n, 'samples': samples, 'seed': seed,
            'accuracy_off': round(point_off, 4), 'accuracy_off_ci': interval(off),
            'accuracy_on': round(point_on, 4), 'accuracy_on_ci': interval(on),
            'lift': round(point_on - point_off, 4), 'lift_ci': interval(lift),
            'fixed_by_memory': sum(not a and b for a, b in pairs), 'broken_by_memory': sum(a and not b for a, b in pairs)}
