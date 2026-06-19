"""Pilot seed + console route tests (PR 10)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import ApiKey, User
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, ROLE_KEYS, seed_pilot
from services import rbac_service


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def test_seed_is_idempotent():
    with _factory()() as s:
        first = seed_pilot(s)
        second = seed_pilot(s)  # second run must not duplicate
        users = s.query(User).filter(User.tenant_id == DEMO_TENANT_ID).count()
        keys = s.query(ApiKey).filter(ApiKey.tenant_id == DEMO_TENANT_ID).count()

    assert users == len(ROLE_KEYS) == 4
    assert keys == len(ROLE_KEYS) == 4
    assert first["sample_run_id"] == second["sample_run_id"]  # run reused, not recreated
    assert {c["role"] for c in first["credentials"]} == {"Admin", "Operator", "Reviewer", "Auditor"}


def test_seeded_keys_resolve_to_correct_tenant_and_permissions():
    with _factory()() as s:
        seed_pilot(s)
        op = rbac_service.resolve_principal(s, api_key="pilot-operator-key")
        rev = rbac_service.resolve_principal(s, api_key="pilot-reviewer-key")
        aud = rbac_service.resolve_principal(s, api_key="pilot-auditor-key")

    assert op.tenant_id == DEMO_TENANT_ID and op.has("create_governed_action")
    assert rev.has("approve_action") and not rev.has("create_governed_action")
    assert aud.has("view_audit") and aud.has("export_evidence")


def test_console_route_serves_html():
    with TestClient(app) as client:
        r = client.get("/console")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Pilot Control Console" in r.text


def test_role_separation_for_pilot_keys():
    """Operator can't approve; Auditor can't submit but can export; Reviewer can't submit."""
    with _factory()() as s:
        seed_pilot(s)
    high = {
        "vendor_name": "VendorX", "system_type": "autonomous agent", "intended_use": "outreach",
        "data_sensitivity": "regulated", "external_exposure": True, "autonomy_level": "autonomous",
    }
    with TestClient(app) as client:
        r = client.post("/workflows/vendor-governance-review", json=high,
                        headers={"X-Api-Key": "pilot-operator-key"})
        gid, approval_id = r.json()["governed_action_id"], r.json()["approval_id"]

        # Operator lacks approve_action.
        assert client.post(f"/approvals/{approval_id}/approve", json={"actor": "op"},
                           headers={"X-Api-Key": "pilot-operator-key"}).status_code == 403
        # Reviewer lacks create_governed_action.
        assert client.post("/workflows/vendor-governance-review", json=high,
                           headers={"X-Api-Key": "pilot-reviewer-key"}).status_code == 403
        # Auditor lacks create but can export evidence.
        assert client.post("/workflows/vendor-governance-review", json=high,
                           headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 403
        assert client.get(f"/evidence/packets/export/{gid}?format=json",
                          headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 200


def test_console_loop_via_seeded_keys():
    """End-to-end through the API the console calls, using seeded keys."""
    with _factory()() as s:
        seed_pilot(s)

    with TestClient(app) as client:
        # Operator submits (high-risk -> approval required).
        r = client.post(
            "/workflows/vendor-governance-review",
            json={
                "vendor_name": "VendorX", "system_type": "autonomous agent",
                "intended_use": "outreach", "data_sensitivity": "regulated",
                "external_exposure": True, "autonomy_level": "autonomous",
            },
            headers={"X-Api-Key": "pilot-operator-key"},
        )
        assert r.status_code == 200
        gid, approval_id = r.json()["governed_action_id"], r.json()["approval_id"]
        assert approval_id

        # Reviewer approves.
        assert client.post(f"/approvals/{approval_id}/approve", json={"actor": "rev"},
                           headers={"X-Api-Key": "pilot-reviewer-key"}).status_code == 200
        # Auditor exports the packet.
        assert client.get(f"/evidence/packets/export/{gid}?format=md",
                          headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 200
