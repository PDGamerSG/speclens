"""Team-scoped immutable imports; evaluation never spends provider budget."""
from fastapi import APIRouter, Request

from .auth import actor_for, require_identity
from .store import PilotStore
from .validation import ValidationImport, evaluate_validation

router = APIRouter(prefix='/api/workspace/pilot', tags=['Factory validation'])


def _store() -> PilotStore:
    # Follow the same engine as the workspace and auth, including isolated tests.
    from ..workspace.routes import service
    return PilotStore(service.store.engine)


@router.get('/validation')
def validation_runs(request: Request):
    identity = require_identity(request)
    return {'runs': _store().list(identity['team']['id'], 'validation')}


@router.post('/validation', status_code=201)
def import_validation(body: ValidationImport, request: Request):
    identity = require_identity(request, roles={'admin', 'engineer'})
    return _store().create(identity['team']['id'], 'validation', evaluate_validation(body),
                           actor=actor_for(identity))
