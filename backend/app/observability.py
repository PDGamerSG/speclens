"""Logs, request IDs and error reporting for the API, worker and cron jobs.

- Every response carries X-Request-ID. A valid incoming ID is kept, so one ID follows a request from Vercel
  through the API into the job it queues.
- LOG_FORMAT=json, or running on Render, writes one JSON object per log line for log search.
- SENTRY_DSN turns on Sentry. No request bodies or personal data are sent.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import time
import uuid

request_id: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')
_VALID_ID = re.compile(r'^[A-Za-z0-9._\-]{8,64}$')
_configured = False


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {'time': time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(record.created)) + f'.{int(record.msecs):03d}Z',
                 'level': record.levelname, 'logger': record.name, 'message': record.getMessage()}
        if rid := getattr(record, 'request_id', ''):
            entry['request_id'] = rid
        if record.exc_info:
            entry['error'] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id.get()
        return True


def setup(component: str) -> None:
    """Configure logging and Sentry once per process."""
    global _configured
    if _configured:
        return
    _configured = True
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    if os.environ.get('LOG_FORMAT', 'json' if os.environ.get('RENDER') else 'text') == 'json':
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    root = logging.getLogger('speclens')
    root.setLevel(os.environ.get('LOG_LEVEL', 'INFO'))
    root.addHandler(handler)
    root.propagate = False
    if dsn := os.environ.get('SENTRY_DSN', '').strip():
        import sentry_sdk
        sentry_sdk.init(dsn=dsn, environment=os.environ.get('SENTRY_ENVIRONMENT', 'production'),
                        release=os.environ.get('RENDER_GIT_COMMIT') or None, send_default_pii=False,
                        traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0.1')),
                        server_name=component)


class RequestIdMiddleware:
    """Pure ASGI, so streaming responses pass through untouched."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        incoming = dict(scope.get('headers') or []).get(b'x-request-id', b'').decode('latin-1')
        rid = incoming if _VALID_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = request_id.set(rid)

        async def send_with_id(message):
            if message['type'] == 'http.response.start':
                headers = [(k, v) for k, v in message.get('headers', []) if k.lower() != b'x-request-id']
                message = {**message, 'headers': headers + [(b'x-request-id', rid.encode())]}
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id.reset(token)
