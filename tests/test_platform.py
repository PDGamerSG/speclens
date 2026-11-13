"""Platform pieces for the Render deployment: health probe, container image and Blueprint."""
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


def test_health_probe_answers_without_reading_records(monkeypatch):
    from app import public
    from app.main import app
    monkeypatch.setattr(public, 'PUBLIC_MODE', True)
    response = TestClient(app).get('/healthz')
    assert response.status_code == 200
    assert response.json() == {'ok': True}


def test_api_image_has_no_frontend_stage_and_binds_the_platform_port():
    dockerfile = (ROOT / 'backend' / 'Dockerfile').read_text()
    assert 'node' not in dockerfile
    assert '${PORT:-8770}' in dockerfile
    assert 'USER speclens' in dockerfile
