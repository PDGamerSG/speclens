"""Public demo boundaries: per-browser memory, bounded calls, and same-origin writes."""
from __future__ import annotations

import hashlib
import os
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.formparsers import MultiPartException
from starlette.middleware.base import BaseHTTPMiddleware

PUBLIC_MODE = os.environ.get('CHIEF_SKILL_PUBLIC', '0') == '1'
CALL_LIMIT = 30
WINDOW = 3600
COOKIE = 'chief_skill_workspace'
MAX_BODY = 9 * 1024 * 1024
limiter: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()
_tokens = re.compile(r'^[a-f0-9]{64}$')


def owner(request: Request) -> str:
    return getattr(request.state, 'workspace_owner', '')


def allow_call(visitor: str, address: str) -> bool:
    current = time.monotonic()
    with _lock:
        for key in list(limiter):
            while limiter[key] and limiter[key][0] <= current - WINDOW:
                limiter[key].popleft()
            if not limiter[key]:
                del limiter[key]
        for key, limit in ((f'visitor:{visitor}', CALL_LIMIT), (f'ip:{address}', CALL_LIMIT * 4)):
            if len(limiter[key]) >= limit:
                return False
        limiter[f'visitor:{visitor}'].append(current)
        limiter[f'ip:{address}'].append(current)
        return True


class PublicWorkspaceMiddleware(BaseHTTPMiddleware):
    async def __call__(self, scope, receive, send):
        if not PUBLIC_MODE or scope['type'] != 'http':
            return await super().__call__(scope, receive, send)
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            if message['type'] == 'http.request':
                size += len(message.get('body', b''))
                if size > MAX_BODY:
                    scope.setdefault('state', {})['body_too_large'] = True
                    # Starlette closes already-spooled files for this exception.
                    raise MultiPartException('Choose an image smaller than 8 MB.')
            return message

        return await super().__call__(scope, limited_receive, send)

    async def dispatch(self, request: Request, call_next):
        if not PUBLIC_MODE:
            return await call_next(request)
        cookie = request.cookies.get(COOKIE, '')
        visitor = cookie if _tokens.fullmatch(cookie) else secrets.token_hex(32)
        # Records and JSON exports contain an identifier, never the bearer cookie.
        request.state.workspace_owner = hashlib.sha256(visitor.encode()).hexdigest()
        path = request.url.path
        if ((path.startswith('/api/') and not path.startswith('/api/workspace/') and path != '/api/health')
                or (path.startswith('/files/') and not path.startswith(('/files/fixtures/', '/files/workspace/')))):
            response = JSONResponse({'detail': 'Not found.'}, status_code=404)
        elif request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('origin') and (
                urlsplit(request.headers['origin']).netloc != request.url.netloc):
            response = JSONResponse({'detail': 'Open this workspace directly to make changes.'}, status_code=403)
        elif request.method == 'POST' and not allow_call(visitor, request.client.host if request.client else 'unknown'):
            response = JSONResponse({'detail': 'This public workspace has reached its hourly request limit. Please try again later.'},
                                    status_code=429, headers={'Retry-After': str(WINDOW)})
        elif request.headers.get('content-length', '').isdigit() and int(request.headers['content-length']) > MAX_BODY:
            response = JSONResponse({'detail': 'Choose an image smaller than 8 MB.'}, status_code=413)
        else:
            response = await call_next(request)
            if getattr(request.state, 'body_too_large', False):
                response = JSONResponse({'detail': 'Choose an image smaller than 8 MB.'}, status_code=413)
        if cookie != visitor:
            response.set_cookie(COOKIE, visitor, max_age=30 * 86400, httponly=True,
                                secure=request.url.scheme == 'https', samesite='lax')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; img-src 'self' blob: data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        if path.startswith(('/api/', '/files/workspace/')):
            response.headers['Cache-Control'] = 'no-store'
        return response
