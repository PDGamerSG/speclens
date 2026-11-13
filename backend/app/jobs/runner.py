"""What each job kind does. The same code runs in the API's thread pool and in the worker."""
from __future__ import annotations

from typing import Callable

import hashlib

from openai import APIError

from ..meta import ledger
from ..meta.client import MetaAPIError
from ..workspace.memory import MemoryUnavailable
from ..workspace.store import Scope
from .queue import JobFailed

MODEL_FAILED = 'The vision model could not complete this inspection. Check the model connection and try again.'


def failure(error: Exception) -> JobFailed | None:
    """The HTTP status and message a known failure maps to, or None for an unexpected error."""
    if isinstance(error, JobFailed):
        return error
    if isinstance(error, MemoryUnavailable):
        return JobFailed(503, str(error))
    if isinstance(error, ledger.BudgetExceeded):
        return JobFailed(402, str(error))
    if isinstance(error, (APIError, MetaAPIError)):
        return JobFailed(502, MODEL_FAILED, retryable=True)
    return None


def make_runner(get_service: Callable[[], object]) -> Callable[[dict], dict]:
    def run(job: dict) -> dict:
        service = get_service()
        payload = job['payload']
        if not isinstance(payload.get('upload'), str) or not isinstance(payload.get('scope'), dict):
            raise JobFailed(400, 'This job is missing its photo or scope. Queue it again.')
        scope = Scope(**payload['scope'])
        context = payload.get('context')
        if context:
            from ..pilot.integration import complete_capture
            result_id = 'insp-' + hashlib.sha256(f'{scope.owner_id}:{context["capture_id"]}'.encode()).hexdigest()[:24]
            if (existing := service.store.inspection(result_id)) is not None:
                complete_capture(service.store, existing)
                service.media.delete(payload['upload'])
                return existing
        data = service.media.get(payload['upload'])
        if data is None:
            raise JobFailed(410, 'The photo for this job is no longer stored. Upload it again.')
        source = payload.get('source', {})
        try:
            if job['kind'] == 'inspect':
                options = {'context': context} if context else {}
                result = service.run(data, payload['filename'], scope, use_memory=payload['use_memory'], **source, **options)
            elif job['kind'] == 'compare':
                result = service.compare(data, payload['filename'], scope,
                                         expected_verdict=payload.get('expected_verdict'),
                                         **({'policy': payload['policy']} if payload.get('policy') else {}), **source)
            else:
                raise JobFailed(400, f'Unknown job kind: {job["kind"]}.')
        except Exception as error:
            mapped = failure(error)
            if mapped is None:
                raise
            raise mapped from None
        service.media.delete(payload['upload'])
        return result

    return run
