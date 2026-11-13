"""Named local accounts, opaque revocable sessions and independent durable auth limits."""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from urllib.parse import urlsplit
import uuid

from fastapi import HTTPException, Request, Response
import sqlalchemy as sa

from .. import db
from . import tables
from .store import PilotStore, now, transaction

COOKIE = 'speclens_session'
SESSION_SECONDS = 7 * 24 * 3600
INVITE_SECONDS = 48 * 3600
AUTH_WINDOW = 900
ROLES = {'admin', 'engineer', 'operator', 'viewer'}


def workspace_engine():
    # Tests and the application share the existing service; no independent global DB.
    from ..workspace.routes import service
    return service.store.engine


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def password_hash(password):
    salt = secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024)
    return f'scrypt$16384$8$1${salt.hex()}${value.hex()}'


def verify_password(password, encoded):
    try:
        algorithm, n, r, p, salt, expected = encoded.split('$')
        if algorithm != 'scrypt' or (int(n), int(r), int(p)) != (16384, 8, 1):
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=int(n), r=int(r), p=int(p),
                                maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(actual, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def check_origin(request: Request):
    if request.method in {'GET', 'HEAD', 'OPTIONS'}:
        return
    origin = request.headers.get('origin')
    if origin:
        parsed = urlsplit(origin)
        trusted = {value.strip().rstrip('/') for value in os.environ.get('SPECLENS_ALLOWED_ORIGINS', '').split(',')
                   if value.strip()}
        same_host = parsed.netloc.lower() == request.url.netloc.lower()
        if (parsed.scheme != request.url.scheme or (not same_host and origin not in trusted)
                or parsed.path not in {'', '/'} or parsed.query or parsed.fragment or parsed.username or parsed.password):
            raise HTTPException(403, 'Cross-origin account and workspace writes are not allowed.')
    if request.headers.get('sec-fetch-site') == 'cross-site':
        raise HTTPException(403, 'Cross-origin account and workspace writes are not allowed.')


def private_response(response: Response):
    response.headers['Cache-Control'] = 'no-store'


def current_identity(request: Request, engine=None):
    token = request.cookies.get(COOKIE)
    if token is None:
        return None
    if not token or len(token) > 200:
        raise HTTPException(401, 'Your session is invalid or expired. Sign in again.')
    engine = engine if engine is not None else workspace_engine()
    query = (sa.select(tables.users.c.id, tables.users.c.username, tables.users.c.name,
                       tables.teams.c.id.label('team_id'), tables.teams.c.name.label('team_name'),
                       tables.memberships.c.role)
             .select_from(tables.sessions.join(tables.users, tables.sessions.c.user_id == tables.users.c.id)
                          .join(tables.teams, tables.sessions.c.team_id == tables.teams.c.id)
                          .join(tables.memberships, sa.and_(
                              tables.memberships.c.user_id == tables.users.c.id,
                              tables.memberships.c.team_id == tables.teams.c.id)))
             .where(tables.sessions.c.token_hash == token_hash(token), tables.sessions.c.revoked_at.is_(None),
                    tables.sessions.c.expires_at > time.time(), tables.memberships.c.active.is_(True)))
    with engine.connect() as connection:
        row = connection.execute(query).mappings().first()
    if row is None:
        raise HTTPException(401, 'Your session is invalid or expired. Sign in again.')
    return {'user': {key: row[key] for key in ('id', 'username', 'name')},
            'team': {'id': row['team_id'], 'name': row['team_name']}, 'role': row['role']}


def require_identity(request: Request, roles=None):
    check_origin(request)
    identity = current_identity(request)
    if identity is None:
        raise HTTPException(401, 'Sign in to the factory workspace.')
    if roles is not None and identity['role'] not in roles:
        raise HTTPException(403, 'Your team role does not permit this action.')
    return identity


def actor_for(identity):
    return {**identity['user'], 'role': identity['role']}


def session_payload(identity):
    return {'authenticated': identity is not None, 'user': identity['user'] if identity else None,
            'team': identity['team'] if identity else None, 'role': identity['role'] if identity else None}


def _session(connection, user_id, team_id):
    token = secrets.token_urlsafe(48)
    connection.execute(tables.sessions.insert().values(
        token_hash=token_hash(token), user_id=user_id, team_id=team_id, created_at=now(),
        expires_at=time.time() + SESSION_SECONDS))
    return token


def set_session(response: Response, request: Request, token):
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == 'https', samesite='strict', path='/')


def auth_limit(request, action, username=''):
    """Persist counters separately from the optional anonymous demo quota.

    Counters are atomic across API processes, including failed attempts. Only hashes
    of addresses/usernames are stored. A new cookie cannot reset them.
    """
    from ..public import client_address
    bucket = int(time.time() // AUTH_WINDOW)
    keys = [(f'auth:ip:{client_address(request)}', 80),
            (f'auth:{action}:ip:{client_address(request)}', 40)]
    if username:
        keys.append((f'auth:{action}:user:{username.casefold()}', 12))
    allowed = True
    engine = workspace_engine()
    with transaction(engine) as connection:
        connection.execute(tables.auth_limits.delete().where(tables.auth_limits.c.window < bucket - 4))
        for key, limit in keys:
            id = token_hash(key)
            db.upsert_ignore(connection, tables.auth_limits, {'id': id, 'window': bucket, 'attempts': 0})
            connection.execute(tables.auth_limits.update().where(
                tables.auth_limits.c.id == id, tables.auth_limits.c.window != bucket).values(window=bucket, attempts=0))
            count = connection.execute(tables.auth_limits.update().where(tables.auth_limits.c.id == id).values(
                attempts=tables.auth_limits.c.attempts + 1).returning(tables.auth_limits.c.attempts)).scalar_one()
            if count > limit:
                allowed = False
    if not allowed:
        raise HTTPException(429, 'Too many account attempts. Try again in 15 minutes.', headers={'Retry-After': str(AUTH_WINDOW)})


def register_account(username, password, name, team_name):
    engine = workspace_engine()
    user = {'id': f'user-{uuid.uuid4().hex}', 'username': username.casefold(), 'name': name}
    team = {'id': f'team-{uuid.uuid4().hex}', 'name': team_name}
    encoded = password_hash(password)
    try:
        with transaction(engine) as connection:
            connection.execute(tables.users.insert().values(**user, password_hash=encoded, created_at=now()))
            connection.execute(tables.teams.insert().values(**team, created_at=now()))
            connection.execute(tables.memberships.insert().values(
                id=f'member-{uuid.uuid4().hex}', team_id=team['id'], user_id=user['id'],
                role='admin', active=True, version=1, created_at=now()))
            token = _session(connection, user['id'], team['id'])
            identity = {'user': user, 'team': team, 'role': 'admin'}
            PilotStore(engine)._event(connection, team['id'], actor_for(identity), 'team.created', team['id'])
    except sa.exc.IntegrityError:
        raise HTTPException(409, 'That username is already registered.') from None
    return identity, token


def login_account(username, password):
    engine = workspace_engine()
    with engine.connect() as connection:
        user = connection.execute(sa.select(tables.users).where(
            tables.users.c.username == username.casefold())).mappings().first()
    if user is None:
        # Match the password work for existing accounts without keeping a global secret.
        hashlib.scrypt(password.encode(), salt=b'\0' * 16, n=16384, r=8, p=1, maxmem=64 * 1024 * 1024)
        raise HTTPException(401, 'Username or password is incorrect.')
    if not verify_password(password, user['password_hash']):
        raise HTTPException(401, 'Username or password is incorrect.')
    with transaction(engine) as connection:
        membership = connection.execute(sa.select(tables.memberships, tables.teams.c.name.label('team_name'))
            .join(tables.teams, tables.memberships.c.team_id == tables.teams.c.id).where(
                tables.memberships.c.user_id == user['id'], tables.memberships.c.active.is_(True))
            .order_by(tables.memberships.c.created_at, tables.memberships.c.id)).mappings().first()
        if membership is None:
            raise HTTPException(401, 'Username or password is incorrect, or membership is inactive.')
        token = _session(connection, user['id'], membership['team_id'])
        identity = {'user': {key: user[key] for key in ('id', 'username', 'name')},
                    'team': {'id': membership['team_id'], 'name': membership['team_name']}, 'role': membership['role']}
        PilotStore(engine)._event(connection, membership['team_id'], actor_for(identity), 'session.started', user['id'])
    return identity, token


def logout_account(token):
    if token:
        engine = workspace_engine()
        with transaction(engine) as connection:
            connection.execute(tables.sessions.update().where(tables.sessions.c.token_hash == token_hash(token)).values(revoked_at=now()))


def create_invite(identity, role):
    token = secrets.token_urlsafe(36)
    expiry = time.time() + INVITE_SECONDS
    engine = workspace_engine()
    with transaction(engine, identity['team']['id']) as connection:
        id = f'invite-{uuid.uuid4().hex}'
        connection.execute(tables.invites.insert().values(
            id=id, token_hash=token_hash(token), team_id=identity['team']['id'], role=role,
            created_by=identity['user']['id'], created_at=now(), expires_at=expiry))
        PilotStore(engine)._event(connection, identity['team']['id'], actor_for(identity), 'invite.created', id, {'role': role})
    return {'token': token, 'expires_at': expiry}


def join_account(token, username, password, name):
    engine = workspace_engine()
    encoded = password_hash(password)
    user = {'id': f'user-{uuid.uuid4().hex}', 'username': username.casefold(), 'name': name}
    try:
        with transaction(engine) as connection:
            invite = connection.execute(sa.select(tables.invites, tables.teams.c.name.label('team_name')).join(
                tables.teams, tables.invites.c.team_id == tables.teams.c.id).where(
                    tables.invites.c.token_hash == token_hash(token), tables.invites.c.used_at.is_(None),
                    tables.invites.c.expires_at > time.time())).mappings().first()
            if invite is None:
                raise HTTPException(422, 'The invitation is invalid, expired or already used.')
            used = connection.execute(tables.invites.update().where(
                tables.invites.c.id == invite['id'], tables.invites.c.used_at.is_(None),
                tables.invites.c.expires_at > time.time()).values(used_at=now()))
            if used.rowcount != 1:
                raise HTTPException(422, 'The invitation is invalid, expired or already used.')
            connection.execute(tables.users.insert().values(**user, password_hash=encoded, created_at=now()))
            member_id = f'member-{uuid.uuid4().hex}'
            connection.execute(tables.memberships.insert().values(
                id=member_id, team_id=invite['team_id'], user_id=user['id'], role=invite['role'],
                active=True, version=1, created_at=now()))
            token = _session(connection, user['id'], invite['team_id'])
            identity = {'user': user, 'team': {'id': invite['team_id'], 'name': invite['team_name']}, 'role': invite['role']}
            PilotStore(engine)._event(connection, invite['team_id'], actor_for(identity), 'member.joined', member_id,
                                      {'role': invite['role'], 'invite_id': invite['id']})
    except sa.exc.IntegrityError:
        raise HTTPException(409, 'That username is already registered.') from None
    return identity, token


def team_members(identity):
    owner = identity['team']['id']
    engine = workspace_engine()
    with engine.connect() as connection:
        members = connection.execute(sa.select(
            tables.memberships.c.id, tables.memberships.c.user_id, tables.users.c.username, tables.users.c.name,
            tables.memberships.c.role, tables.memberships.c.active, tables.memberships.c.version).join(
                tables.users, tables.memberships.c.user_id == tables.users.c.id).where(
                    tables.memberships.c.team_id == owner).order_by(tables.memberships.c.created_at)).mappings().all()
        invitations = connection.execute(sa.select(
            tables.invites.c.id, tables.invites.c.role, tables.invites.c.expires_at, tables.invites.c.used_at).where(
                tables.invites.c.team_id == owner).order_by(tables.invites.c.created_at.desc())).mappings().all()
    return {'members': [dict(member) for member in members], 'invites': [dict(invite) for invite in invitations]}


def update_member(identity, member_id, version, role, active):
    engine = workspace_engine()
    owner = identity['team']['id']
    with transaction(engine, owner) as connection:
        member = connection.execute(sa.select(tables.memberships).where(
            tables.memberships.c.id == member_id, tables.memberships.c.team_id == owner)).mappings().first()
        if member is None:
            raise HTTPException(404, 'Team member not found.')
        if member['version'] != version:
            raise HTTPException(409, 'This membership changed. Reload before saving.')
        if member['role'] == 'admin' and member['active'] and (role != 'admin' or not active):
            admins = connection.execute(sa.select(sa.func.count()).select_from(tables.memberships).where(
                tables.memberships.c.team_id == owner, tables.memberships.c.role == 'admin',
                tables.memberships.c.active.is_(True))).scalar_one()
            if admins <= 1:
                raise HTTPException(409, 'The team must retain at least one active admin.')
        changed = connection.execute(tables.memberships.update().where(
            tables.memberships.c.id == member_id, tables.memberships.c.version == version).values(
                role=role, active=active, version=version + 1))
        if changed.rowcount != 1:
            raise HTTPException(409, 'This membership changed. Reload before saving.')
        if not active:
            connection.execute(tables.sessions.update().where(
                tables.sessions.c.user_id == member['user_id'], tables.sessions.c.team_id == owner).values(revoked_at=now()))
        PilotStore(engine)._event(connection, owner, actor_for(identity), 'member.updated', member_id,
                                  {'role': role, 'active': active, 'previous_role': member['role'], 'previous_active': member['active']})
        user = connection.execute(sa.select(tables.users).where(tables.users.c.id == member['user_id'])).mappings().one()
    return {'id': member_id, 'user_id': user['id'], 'username': user['username'], 'name': user['name'],
            'role': role, 'active': active, 'version': version + 1}
