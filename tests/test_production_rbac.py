"""Production RBAC hardening tests (PR 13).

In production (and staging) the no-API-key operator bypass is disabled: every
protected action requires an authenticated principal. Demo mode preserves the
bypass for local use.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.main import app
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, seed_pilot
from services import governance_workflow

HIGH = {
    "vendor_name": "VendorX", "system_type": "autonomous agent", "intended_use": "outreach",
    "data_sensitivity": "regulated", "external_exposure": True, "autonomy_level": "autonomous",
}


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _seed_and_get_ids():
    with _factory()() as s:
        seed_pilot(s)
        runs = governance_workflow.list_runs(s, tenant_id=DEMO_TENANT_ID)
        gid = runs[0]["governed_action_id"]
        approval_id = runs[0]["approval_id"]
    return gid, approval_id


def test_production_denies_unauthenticated(monkeypatch):
    gid, _ = _seed_and_get_ids()
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            # No API key -> no bypass -> every protected action denied.
            assert client.post("/workflows/vendor-governance-review", json=HIGH).status_code == 403
            assert client.get("/workflows/runs").status_code == 403
            assert client.get("/audit").status_code == 403
            assert client.get(f"/evidence/packets/export/{gid}?format=json").status_code == 403
            # Authenticated principal still works.
            assert client.post("/workflows/vendor-governance-review", json=HIGH,
                               headers={"X-Api-Key": "pilot-operator-key"}).status_code == 200
            assert client.get(f"/evidence/packets/export/{gid}?format=json",
                              headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 200
    finally:
        get_settings.cache_clear()


def test_production_requires_auth_for_approval(monkeypatch):
    _, approval_id = _seed_and_get_ids()
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            assert client.post(f"/approvals/{approval_id}/approve", json={"actor": "x"}).status_code == 403
            assert client.post(f"/approvals/{approval_id}/approve", json={"actor": "rev"},
                               headers={"X-Api-Key": "pilot-reviewer-key"}).status_code == 200
    finally:
        get_settings.cache_clear()


def test_staging_also_disables_bypass(monkeypatch):
    _seed_and_get_ids()
    monkeypatch.setenv("APP_ENV", "staging")
    get_settings.cache_clear()
    try:
        with TestClient(app) as client:
            assert client.post("/workflows/vendor-governance-review", json=HIGH).status_code == 403
    finally:
        get_settings.cache_clear()


def test_demo_preserves_operator_bypass():
    _seed_and_get_ids()  # default env is demo
    with TestClient(app) as client:
        assert client.post("/workflows/vendor-governance-review", json=HIGH).status_code == 200
        assert client.get("/audit").status_code == 200
