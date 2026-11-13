"""What each job kind does. The same code runs in the API's thread pool and in the worker."""
from __future__ import annotations

from typing import Callable

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
        data = service.media.get(payload['upload'])
        if data is None:
            raise JobFailed(410, 'The photo for this job is no longer stored. Upload it again.')
        scope = Scope(**payload['scope'])
        source = payload.get('source', {})
        try:
            if job['kind'] == 'inspect':
                result = service.run(data, payload['filename'], scope, use_memory=payload['use_memory'], **source)
            elif job['kind'] == 'compare':
                result = service.compare(data, payload['filename'], scope,
                                         expected_verdict=payload.get('expected_verdict'), **source)
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
