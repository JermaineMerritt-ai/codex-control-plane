"""Incident replay tests (PR 17 — read-only)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, seed_pilot
from services import (
    governance_workflow,
    incident_replay,
    override_service,
    policy_version_service,
    tenant_service,
)


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _high_risk(session, tenant):
    return governance_workflow.submit_vendor_governance_review(
        session, tenant_id=tenant, actor="operator", vendor_name="VendorX",
        system_type="autonomous agent", intended_use="outreach", data_sensitivity="regulated",
        external_exposure=True, autonomy_level="autonomous",
    )["governed_action_id"]


def test_replay_reconstructs_full_context():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        policy_version_service.seed_default_policy(s)  # app seeds this at startup
        gid = _high_risk(s, "A")
        override_service.create_override(
            s, tenant_id="A", governed_action_id=gid, overridden_by="admin",
            reason="pilot", authority_basis="compliance lead", compensating_control="weekly audit",
        )
        replay = incident_replay.build_incident_replay(s, governed_action_id=gid, tenant_id="A")

    assert replay["incident"]["governed_action_id"] == gid
    assert replay["original_request"]["vendor_name"] == "VendorX"
    assert replay["risk"]["level"] == "high"
    assert replay["policy"]["policy_version_id"]  # bound version
    assert replay["approvals"]  # high-risk created an approval
    assert replay["overrides"]  # override recorded
    assert replay["model_vendor_tool"]["status"] == "not_recorded"  # deferred, not invented
    assert replay["audit_chain_verification"]["status"] == "verified"
    # Timeline ordered by seq and includes the submit event.
    seqs = [e["seq"] for e in replay["audit_timeline"]]
    assert seqs == sorted(seqs)
    assert any(e["action"] == "governance_review.submitted" for e in replay["audit_timeline"])


def test_replay_renders_json_and_markdown():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _high_risk(s, "A")
        replay = incident_replay.build_incident_replay(s, governed_action_id=gid, tenant_id="A")
    parsed = json.loads(incident_replay.render_json(replay))
    assert parsed["incident"]["governed_action_id"] == gid
    md = incident_replay.render_markdown(replay)
    assert md.startswith("# Incident Replay")
    assert "Audit timeline" in md and "not_recorded" in md


def test_replay_tenant_isolation():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        gid = _high_risk(s, "A")
        assert incident_replay.build_incident_replay(s, governed_action_id=gid, tenant_id="B") is None
        assert incident_replay.build_incident_replay(s, governed_action_id=gid, tenant_id="A") is not None


def test_replay_endpoint_rbac_and_formats():
    with _factory()() as s:
        seed_pilot(s)
        gid = governance_workflow.list_runs(s, tenant_id=DEMO_TENANT_ID)[0]["governed_action_id"]
        # A tenant key with no user => no permissions.
        tenant_service.provision_api_key(s, tenant_id=DEMO_TENANT_ID, name="nouser", raw_key="nouser-pilot")

    with TestClient(app) as client:
        # Auditor (view_audit) can read JSON + Markdown.
        j = client.get(f"/incidents/{gid}/replay", headers={"X-Api-Key": "pilot-auditor-key"})
        assert j.status_code == 200 and j.json()["incident"]["governed_action_id"] == gid
        md = client.get(f"/incidents/{gid}/replay?format=md", headers={"X-Api-Key": "pilot-auditor-key"})
        assert md.status_code == 200 and md.text.startswith("# Incident Replay")
        # No view_audit -> 403.
        assert client.get(f"/incidents/{gid}/replay", headers={"X-Api-Key": "nouser-pilot"}).status_code == 403
        # Unknown action -> 404.
        assert client.get("/incidents/nope/replay", headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 404
