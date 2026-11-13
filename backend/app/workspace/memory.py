"""Small HTTP adapter for the documented Hindsight retain / recall / reflect API."""
from __future__ import annotations

import time

import httpx

from .store import Scope


RETRY_STATUS = {429, 503}
MAX_WAIT = 4.0  # seconds; an inspection must not hang on memory


class MemoryUnavailable(RuntimeError):
    pass


def retry_wait(response: httpx.Response, attempt: int) -> float:
    """Seconds to wait before retrying a rate-limited request: Retry-After if given in seconds, capped."""
    try:
        wait = float(response.headers.get('retry-after') or 0)
    except ValueError:  # Retry-After may also be an HTTP date
        wait = 0.0
    return min(wait if wait > 0 else 1.0 * (attempt + 1), MAX_WAIT)


class HindsightMemory:
    def __init__(self, base_url: str, api_key: str = '', *, transport=None):
        self.base_url = base_url.rstrip('/')
        self.api_key = api_key
        self.transport = transport
        self.sleep = time.sleep  # swapped in tests so retries do not wait

    @property
    def configured(self) -> bool:
        return bool(self.base_url) and (self.base_url != 'https://api.hindsight.vectorize.io' or bool(self.api_key))

    def _post(self, scope: Scope, path: str, payload: dict, *, empty_if_missing=False, retries=0) -> dict:
        """POST to a bank. With retries, a 429 or 503 is retried after a short wait before it fails."""
        if not self.configured:
            raise MemoryUnavailable('Connect Hindsight in the server settings to use memory, or switch memory off for a baseline inspection.')
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        try:
            for attempt in range(retries + 1):
                with httpx.Client(timeout=httpx.Timeout(120, connect=8), headers=headers, transport=self.transport) as client:
                    response = client.post(f'{self.base_url}/v1/default/banks/{scope.bank_id}/{path}', json=payload)
                if response.status_code not in RETRY_STATUS or attempt == retries:
                    break
                self.sleep(retry_wait(response, attempt))
            if empty_if_missing and response.status_code == 404:
                missing = response.json()
                detail = missing.get('detail', '') if isinstance(missing, dict) else ''
                if (isinstance(detail, str) and scope.bank_id in detail
                        and 'bank' in detail.casefold()
                        and any(term in detail.casefold() for term in ('not found', 'does not exist'))):
                    return {'results': []}
            response.raise_for_status()
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError('Invalid Hindsight response.')
            return data
        except (httpx.HTTPError, ValueError) as e:
            code = getattr(getattr(e, 'response', None), 'status_code', None)
            if code in (401, 403):
                message = 'Hindsight rejected the server credentials. Update HINDSIGHT_API_KEY and restart the server.'
            elif code == 429:
                message = 'Hindsight is busy. Your correction is safe; retry memory sync shortly.'
            else:
                message = 'Hindsight could not complete this request. Check the memory connection and retry.'
            raise MemoryUnavailable(message) from None

    def _delete(self, path: str) -> None:
        """DELETE a bank or document. Something already gone counts as deleted."""
        if not self.configured:
            raise MemoryUnavailable('Connect Hindsight in the server settings to delete memory.')
        headers = {'Authorization': f'Bearer {self.api_key}'} if self.api_key else {}
        try:
            with httpx.Client(timeout=httpx.Timeout(60, connect=8), headers=headers, transport=self.transport) as client:
                response = client.delete(f'{self.base_url}/v1/default/banks/{path}')
            if response.status_code != 404:
                response.raise_for_status()
        except httpx.HTTPError:
            raise MemoryUnavailable('Hindsight could not delete this memory. Retry shortly.') from None

    def forget(self, bank_id: str, document_id: str) -> None:
        self._delete(f'{bank_id}/documents/{document_id}')

    def drop_bank(self, bank_id: str) -> None:
        self._delete(bank_id)

    def retain(self, scope: Scope, correction: dict) -> dict:
        text = (f'Quality engineer correction for {scope.part_family} at {scope.factory}.\n'
                f'Correction ID: {correction["id"]}. Source inspection: {correction["inspection_id"]}.\n'
                f'The inspector originally decided {correction.get("original_verdict", "unknown")} and reasoned: '
                f'{correction["original_rationale"]}\n'
                f'The quality engineer {correction["reviewer"]} corrected the decision to '
                f'{correction["verdict"]}, defect class {correction["defect_type"]}.\n'
                f'Apply this visual quality standard to future matching parts: {correction["rule_text"]}\n'
                'This is a clarification of the part specification, not permission to bypass other reject clauses.')
        data = self._post(scope, 'memories', {'async': False, 'items': [{
            'content': text, 'context': f'Visual quality standards for {scope.part_family} at {scope.factory}',
            'document_id': correction['id'], 'update_mode': 'replace',
            'metadata': {'correction_id': correction['id'], 'inspection_id': correction['inspection_id'],
                         'scope_id': scope.id, 'reviewer': correction['reviewer']},
            'tags': ['quality-standard', f'scope:{scope.id}'],
        }]})
        if data.get('success') is not True:
            raise MemoryUnavailable('Hindsight did not confirm the correction. It remains pending and can be retried.')
        return data

    def recall(self, scope: Scope) -> list[dict]:
        data = self._post(scope, 'memories/recall', {
            'query': f'Which visual quality standards and human corrections must be applied when inspecting {scope.part_family}? Include ink markings, white print versus gloss, holes, cracks, cuts, and acceptable natural texture.',
            'types': ['world', 'experience'], 'budget': 'mid', 'max_tokens': 1800,
        }, empty_if_missing=True, retries=2)
        rows = data.get('results')
        if not isinstance(rows, list):
            raise MemoryUnavailable('Hindsight returned an unreadable recall result. Retry before inspecting with memory.')
        result = []
        for fact in rows:
            if not isinstance(fact, dict) or not isinstance(fact.get('text'), str):
                continue
            metadata = fact.get('metadata') or {}
            source = fact.get('document_id') or metadata.get('correction_id')
            if source:
                result.append({'id': str(fact.get('id', source)), 'text': fact['text'][:4000],
                               'source_id': str(source), 'type': fact.get('type', 'world')})
        return result[:12]

    def reflect(self, scope: Scope) -> dict:
        data = self._post(scope, 'reflect', {
            'query': f'Summarize the specific visual quality standards learned from quality engineer corrections for {scope.part_family} at {scope.factory}. State only standards supported by these corrections. Cite the source correction IDs. If none exist, say no corrections have been learned yet. Never claim a measured accuracy improvement.',
            'budget': 'low', 'max_tokens': 1000, 'include': {'facts': {}},
        }, retries=2)
        if not isinstance(data.get('text'), str):
            raise MemoryUnavailable('Hindsight did not return a standards summary. Retry shortly.')
        return {'summary': data['text'], 'facts': data.get('facts', []), 'bank_id': scope.bank_id}
