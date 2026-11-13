"""Public demo boundaries: per-browser memory, bounded calls, and same-origin writes."""
from __future__ import annotations

import hashlib
import ipaddress
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

PUBLIC_MODE = os.environ.get('SPECLENS_PUBLIC', os.environ.get('CHIEF_SKILL_PUBLIC', '0')) == '1'
CALL_LIMIT = 30
WINDOW = 3600
COOKIE = 'speclens_workspace'
LEGACY_COOKIE = 'chief_skill_workspace'
MAX_BODY = 9 * 1024 * 1024
GENERATED_DOCS = {'/docs', '/docs/oauth2-redirect', '/redoc', '/openapi.json'}
COMPARE = '/api/workspace/compare'  # Two vision calls, so it counts twice.
limiter: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()
_tokens = re.compile(r'^[a-f0-9]{64}$')


def owner(request: Request) -> str:
    return getattr(request.state, 'workspace_owner', '')


def client_address(request: Request) -> str:
    """The address the hourly limit counts. Anyone can send x-real-ip, so only the trusted proxy may name a visitor."""
    peer = request.client.host if request.client else 'unknown'
    expected = os.environ.get('SPECLENS_PROXY_SECRET', '')
    supplied = request.headers.get('x-speclens-proxy-secret', '')
    if not expected or not secrets.compare_digest(supplied.encode(), expected.encode()):
        return peer
    try:
        address = ipaddress.ip_address(request.headers.get('x-real-ip', '').strip())
    except ValueError:
        return peer
    # One IPv6 customer usually holds a whole /64, so a single address would be trivial to rotate.
    return str(ipaddress.ip_network(f'{address}/64', strict=False)) if address.version == 6 else str(address)


class LimiterUnavailable(RuntimeError):
    pass


class RedisLimiter:
    """Fixed hourly windows in Render Key Value, shared by every API instance.

    INCRBY is atomic. If either counter passes its limit, the increments are undone and the call is refused.
    A window can admit up to twice the limit across its boundary, which is acceptable for abuse control.
    """

    def __init__(self, url: str, client=None):
        if client is None:
            import redis
            client = redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)
        self.client = client

    def allow(self, counters: list[tuple[str, int]], cost: int) -> bool:
        window = int(time.time() // WINDOW)
        names = [f'speclens:limit:{key}:{window}' for key, _ in counters]
        try:
            pipe = self.client.pipeline()
            for name in names:
                pipe.incrby(name, cost)
                pipe.expire(name, WINDOW * 2)
            counts = pipe.execute()[0::2]
            if all(count <= limit for count, (_, limit) in zip(counts, counters)):
                return True
            pipe = self.client.pipeline()
            for name in names:
                pipe.decrby(name, cost)
            pipe.execute()
            return False
        except Exception as error:
            raise LimiterUnavailable('The request limiter is unavailable. Try again shortly.') from error


_redis: RedisLimiter | None = None


def shared_limiter() -> RedisLimiter | None:
    global _redis
    url = os.environ.get('REDIS_URL', '').strip()
    if not url:
        return None
    if _redis is None:
        _redis = RedisLimiter(url)
    return _redis


def allow_call(visitor: str, address: str, cost: int = 1) -> bool:
    counters = [(f'visitor:{visitor}', CALL_LIMIT), (f'ip:{address}', CALL_LIMIT * 4)]
    if (shared := shared_limiter()) is not None:
        return shared.allow(counters, cost)
    current = time.monotonic()
    with _lock:
        for key in list(limiter):
            while limiter[key] and limiter[key][0] <= current - WINDOW:
                limiter[key].popleft()
            if not limiter[key]:
                del limiter[key]
        for key, limit in counters:
            if len(limiter[key]) + cost > limit:
                return False
        limiter[f'visitor:{visitor}'].extend([current] * cost)
        limiter[f'ip:{address}'].extend([current] * cost)
        return True


def _allowed(visitor: str, request: Request, path: str) -> bool | None:
    """True or False from the limiter, or None when the shared limiter cannot be reached, so writes stop safely."""
    try:
        return allow_call(visitor, client_address(request), 2 if path == COMPARE else 1)
    except LimiterUnavailable:
        return None


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
        legacy = request.cookies.get(LEGACY_COOKIE, '')
        visitor = cookie if _tokens.fullmatch(cookie) else legacy if _tokens.fullmatch(legacy) else secrets.token_hex(32)
        # Records and JSON exports contain an identifier, never the bearer cookie.
        request.state.workspace_owner = hashlib.sha256(visitor.encode()).hexdigest()
        path = request.url.path
        if ((path.startswith('/api/') and not path.startswith('/api/workspace/') and path != '/api/health')
                or path in GENERATED_DOCS
                or (path.startswith('/files/') and not path.startswith(('/files/fixtures/', '/files/workspace/')))):
            response = JSONResponse({'detail': 'Not found.'}, status_code=404)
        elif request.method not in {'GET', 'HEAD', 'OPTIONS'} and request.headers.get('origin') and (
                urlsplit(request.headers['origin']).netloc != request.url.netloc
                and request.headers['origin'] not in {
                    value.strip().rstrip('/') for value in os.environ.get('SPECLENS_ALLOWED_ORIGINS', '').split(',')
                    if value.strip()
                }):
            response = JSONResponse({'detail': 'Open this workspace directly to make changes.'}, status_code=403)
        elif request.method == 'POST' and not (allowed := _allowed(visitor, request, path)):
            if allowed is None:
                response = JSONResponse({'detail': 'The request limiter is unavailable. Try again shortly.'}, status_code=503)
            else:
                response = JSONResponse({'detail': 'This public workspace has reached its hourly request limit. Please try again later.'},
                                        status_code=429, headers={'Retry-After': str(WINDOW)})
        elif request.headers.get('content-length', '').isdigit() and int(request.headers['content-length']) > MAX_BODY:
            response = JSONResponse({'detail': 'Choose an image smaller than 8 MB.'}, status_code=413)
        else:
            response = await call_next(request)
            if getattr(request.state, 'body_too_large', False):
                response = JSONResponse({'detail': 'Choose an image smaller than 8 MB.'}, status_code=413)
        # Renewing on API use keeps a returning visitor's workspace past the first 30 days.
        if cookie != visitor or path.startswith('/api/'):
            response.set_cookie(COOKIE, visitor, max_age=30 * 86400, httponly=True,
                                secure=request.url.scheme == 'https', samesite='lax')
        if LEGACY_COOKIE in request.cookies:
            response.delete_cookie(LEGACY_COOKIE, secure=request.url.scheme == 'https', httponly=True, samesite='lax')
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['X-Frame-Options'] = 'DENY'
        if request.url.scheme == 'https':
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; img-src 'self' blob: data:; connect-src 'self'; "
            "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
        if path.startswith(('/api/', '/files/workspace/')):
            response.headers['Cache-Control'] = 'no-store'
        return response
