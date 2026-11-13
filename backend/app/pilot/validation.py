"""Pure paired evaluation of imported, unverified outputs; never calls a provider."""
from __future__ import annotations

import copy
import hashlib
import json
import random
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

OUTPUTS = ('good', 'defect', 'uncertain', 'error')
ARMS = ('baseline', 'with_memory')
RATE_NAMES = ('escaped_defects', 'false_rejects', 'review', 'errors')
EVALUATOR_VERSION = 'factory-validation-v1'
# Fixed bounds keep client-supplied configuration from controlling evaluation work.
MAX_CASES = 2000
BOOTSTRAP_REPLICATES = 1000


class ValidationCase(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    sample_id: str = Field(min_length=1, max_length=120)
    physical_part_id: str = Field(min_length=1, max_length=120)
    lot_id: str = Field(min_length=1, max_length=120)
    session_id: str = Field(min_length=1, max_length=120)
    truth: Literal['good', 'defect']
    severity: Literal['minor', 'major', 'critical'] | None = None
    baseline: Literal['good', 'defect', 'uncertain', 'error']
    with_memory: Literal['good', 'defect', 'uncertain', 'error']


class ValidationImport(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    cases: list[ValidationCase] = Field(min_length=1, max_length=MAX_CASES)
    configuration: dict[str, Any] = Field(default_factory=dict)

    @field_validator('configuration')
    @classmethod
    def bounded_json_configuration(cls, value):
        try:
            encoded = json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':'))
        except (TypeError, ValueError, RecursionError):
            raise ValueError('Configuration must be finite JSON data.') from None
        if len(encoded.encode('utf-8')) > 12000:
            raise ValueError('Configuration is limited to 12,000 UTF-8 bytes.')
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > 8:
                raise ValueError('Configuration nesting is limited to eight levels.')
            children = item.values() if isinstance(item, dict) else item if isinstance(item, list) else []
            pending.extend((child, depth + 1) for child in children)
        return value

    @model_validator(mode='after')
    def matched_parts(self):
        sample_ids = set()
        parts = {}
        for item in self.cases:
            if item.sample_id in sample_ids:
                raise ValueError(f'Duplicate sample_id: {item.sample_id}.')
            sample_ids.add(item.sample_id)
            signature = (item.truth, item.baseline, item.with_memory, item.lot_id, item.severity)
            if item.physical_part_id in parts and parts[item.physical_part_id] != signature:
                raise ValueError('Repeated physical part must have consistent truth, predictions, lot and severity: '
                                 f'{item.physical_part_id}. Import fixed first-attempt results for every view.')
            parts[item.physical_part_id] = signature
        return self


def _rate(count: int, denominator: int) -> dict:
    return {'count': count, 'denominator': denominator, 'rate': count / denominator if denominator else None}


def _summarize(rows: list[dict], arm: str) -> dict:
    matrix = {truth: dict.fromkeys(OUTPUTS, 0) for truth in ('good', 'defect')}
    for item in rows:
        matrix[item['truth']][item[arm]] += 1
    good, defect = sum(matrix['good'].values()), sum(matrix['defect'].values())
    total = good + defect
    review = sum(matrix[truth]['uncertain'] for truth in matrix)
    errors = sum(matrix[truth]['error'] for truth in matrix)
    return {
        'matrix': matrix,
        'escaped_defects': _rate(matrix['defect']['good'], defect),
        'false_rejects': _rate(matrix['good']['defect'], good),
        'review': _rate(review, total),
        'errors': _rate(errors, total),
        'decision_coverage': _rate(total - review - errors, total),
    }


def _clusters(rows: list[dict]) -> list[list[str]]:
    """Parts sharing any lot OR session are dependent, including crossed sessions."""
    parent = {item['physical_part_id']: item['physical_part_id'] for item in rows}

    def find(part):
        while parent[part] != part:
            parent[part] = parent[parent[part]]
            part = parent[part]
        return part

    seen = {}
    for item in rows:
        part = item['physical_part_id']
        for field in ('lot_id', 'session_id'):
            key = (field, item[field])
            if key in seen:
                parent[find(part)] = find(seen[key])
            else:
                seen[key] = part
    groups = defaultdict(list)
    for part in parent:
        groups[find(part)].append(part)
    return list(groups.values())


def _percentile(values: list[float], fraction: float) -> float:
    position = (len(values) - 1) * fraction
    index = int(position)
    return values[index] + (values[min(index + 1, len(values) - 1)] - values[index]) * (position - index)


def _uncertainty(parts: list[dict], groups: list[list[str]], arms: dict) -> dict:
    deltas = {}
    for name in RATE_NAMES:
        before, after = arms['baseline'][name]['rate'], arms['with_memory'][name]['rate']
        deltas[name] = {'estimate': after - before if before is not None else None,
                        'lower': None, 'upper': None}
    result = {
        'method': 'paired_connected_lot_session_cluster_bootstrap', 'confidence': .95,
        'clusters': len(groups), 'replicates': 0, 'delta_rates': deltas,
        'valid_replicates': dict.fromkeys(RATE_NAMES, 0),
        'direction': 'with_memory_minus_baseline',
    }
    if len(groups) < 2:
        return result
    by_part = {item['physical_part_id']: item for item in parts}
    # Precompute cluster sufficient counts: repeated views never enter the sampler.
    summaries = [(_summarize([by_part[part] for part in group], 'baseline'),
                  _summarize([by_part[part] for part in group], 'with_memory')) for group in groups]
    samples = {name: [] for name in RATE_NAMES}
    rng = random.Random(0)
    for _ in range(BOOTSTRAP_REPLICATES):
        # Sample whole connected clusters together and preserve the paired arms.
        chosen = rng.choices(summaries, k=len(summaries))
        for name in RATE_NAMES:
            denominator = sum(before[name]['denominator'] for before, _ in chosen)
            if denominator:
                delta = sum(after[name]['count'] - before[name]['count'] for before, after in chosen)
                samples[name].append(delta / denominator)
    result['replicates'] = BOOTSTRAP_REPLICATES
    for name, values in samples.items():
        if values:
            values.sort()
            deltas[name]['lower'] = _percentile(values, .025)
            deltas[name]['upper'] = _percentile(values, .975)
        result['valid_replicates'][name] = len(values)
    return result


def evaluate_validation(body: ValidationImport) -> dict:
    """Freeze inputs and compute one result per physical part in input order.

    Identifiers and configuration are importer assertions, not checked links to
    production records or proof of label quality, provenance or independence.
    """
    rows = [item.model_dump(exclude_none=True) for item in body.cases]
    selected = {}
    for item in rows:
        selected.setdefault(item['physical_part_id'], item)
    parts = list(selected.values())
    groups = _clusters(rows)
    arms = {arm: _summarize(parts, arm) for arm in ARMS}
    transitions = {output: dict.fromkeys(OUTPUTS, 0) for output in OUTPUTS}
    improvements = regressions = restored = lost = unchanged = 0
    for item in parts:
        before, after, truth = item['baseline'], item['with_memory'], item['truth']
        transitions[before][after] += 1
        unchanged += before == after
        before_resolved, after_resolved = before in ('good', 'defect'), after in ('good', 'defect')
        restored += not before_resolved and after_resolved
        lost += before_resolved and not after_resolved
        if before_resolved and after_resolved:
            improvements += before != truth and after == truth
            regressions += before == truth and after != truth
    limitations = [
        'Imported results, labels, configuration and identifiers are unverified; no live inference was executed.',
        'Input order declares attempt order. Only the first occurrence per physical part is evaluated; '
        'all repeated views must carry identical first-attempt truth and predictions.',
        'No teaching/test leakage or disjointness claim is verified. An importer-supplied assertion is not provenance evidence.',
        'Review (uncertain) and error are unresolved outputs, never correct binary decisions. '
        'Escape and false-reject denominators include all defective and all good physical parts respectively; '
        'Review and error workload use all physical parts.',
        'Connected lot/session clusters preserve observed dependence. Different identifiers do not prove independence '
        'or representative sampling, and unrecorded common sources may still correlate clusters.',
        'Intervals are descriptive paired cluster-bootstrap percentile intervals for memory-minus-baseline rate differences; '
        'they are not release criteria or confidence bounds for a zero observed failure rate.',
        'Bootstrap replicates without the relevant truth class are omitted for that rate; valid_replicates reports '
        'the remaining count. Missing truth classes have no estimated rate or interval.',
    ]
    if len(groups) < 2:
        limitations.append('Fewer than two independent candidate clusters: uncertainty intervals are unavailable.')
    elif len(groups) < 10:
        limitations.append('Few candidate clusters: bootstrap intervals can be unstable or degenerate and do not establish generalization.')
    limitations.append('No factory performance, regulatory compliance or autonomous release claim follows from this import.')
    configuration = copy.deepcopy(body.configuration)
    manifest = {
        'schema_version': 1, 'evaluator_version': EVALUATOR_VERSION,
        'aggregation': 'first_occurrence_per_physical_part', 'input_order_is_attempt_order': True,
        'cases': rows, 'selected_sample_ids': [item['sample_id'] for item in parts],
        'clusters': [{'physical_part_ids': group} for group in groups],
    }
    canonical = json.dumps({'manifest': manifest, 'configuration': configuration},
                           sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    manifest['sha256'] = hashlib.sha256(canonical).hexdigest()
    return {
        'name': body.name, 'source': 'imported_unverified', 'configuration': configuration, 'manifest': manifest,
        'results': {
            'counts': {
                'samples': len(rows), 'physical_parts': len(parts), 'repeated_views': len(rows) - len(parts),
                'lots': len({item['lot_id'] for item in rows}),
                'sessions': len({item['session_id'] for item in rows}), 'clusters': len(groups),
                'truth': {truth: sum(item['truth'] == truth for item in parts) for truth in ('good', 'defect')},
            },
            **arms,
            'paired': {'transitions': transitions, 'resolved_improvements': improvements,
                       'resolved_regressions': regressions, 'restored_decisions': restored,
                       'lost_decisions': lost, 'unchanged': unchanged},
            'uncertainty': _uncertainty(parts, groups, arms), 'limitations': limitations,
        },
    }
