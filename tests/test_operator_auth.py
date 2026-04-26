from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app


def test_operator_key_enforced_when_set(monkeypatch):
    monkeypatch.setenv("OPERATOR_API_KEY", "test-secret-key")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            r = client.get("/jobs")
            assert r.status_code == 401
            assert r.json()["detail"] == "operator_key_required"
            ok = client.get("/jobs", headers={"X-Operator-Key": "test-secret-key"})
            assert ok.status_code == 200
            em = client.get("/email/deliveries", headers={"X-Operator-Key": "test-secret-key"})
            assert em.status_code == 200
            health = client.get("/health")
            assert health.status_code == 200
    finally:
        monkeypatch.delenv("OPERATOR_API_KEY", raising=False)
        get_settings.cache_clear()
