"""Human override registry tests (PR 16).

Authorized override of a high-risk action is recorded (not executed); override
without authority fails; override on a non-high-risk action is rejected; the
override appears in the evidence packet; tenant isolation holds.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, seed_pilot
from services import audit_service, evidence_packet, governance_workflow, override_service


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _high_risk(session, tenant):
    return governance_workflow.submit_vendor_governance_review(
        session, tenant_id=tenant, actor="op", vendor_name="V", system_type="t",
        intended_use="u", data_sensitivity="regulated", external_exposure=True,
        autonomy_level="autonomous",
    )["governed_action_id"]


def _low_risk(session, tenant):
    return governance_workflow.submit_vendor_governance_review(
        session, tenant_id=tenant, actor="op", vendor_name="V", system_type="t",
        intended_use="u", data_sensitivity="internal", external_exposure=False,
        autonomy_level="assisted",
    )["governed_action_id"]


# --- service ---------------------------------------------------------------

def test_override_records_without_executing_and_audits():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _high_risk(s, "A")
        ov = override_service.create_override(
            s, tenant_id="A", governed_action_id=gid, overridden_by="admin",
            reason="time-critical clinical need", authority_basis="CISO delegated authority",
            compensating_control="manual review + 7-day re-evaluation",
        )
        assert ov.status == "override_recorded"
        assert ov.accepted_risk == "high"

        from services import evidence_graph
        action = evidence_graph.get_governed_action(s, gid, tenant_id="A")
        assert action.status == "override_recorded"  # recorded, not "executed"

        events = audit_service.list_for_resource(
            s, resource_type="governed_action", resource_id=gid, tenant_id="A"
        )
        assert any(e.action == "governed_action.overridden" for e in events)


def test_override_not_applicable_for_low_risk():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _low_risk(s, "A")
        try:
            override_service.create_override(
                s, tenant_id="A", governed_action_id=gid, overridden_by="admin",
                reason="x", authority_basis="x", compensating_control="x",
            )
            assert False, "expected override_not_applicable"
        except ValueError as exc:
            assert str(exc) == "override_not_applicable"


def test_override_tenant_isolation():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        gid = _high_risk(s, "A")
        try:
            override_service.create_override(
                s, tenant_id="B", governed_action_id=gid, overridden_by="admin",
                reason="x", authority_basis="x", compensating_control="x",
            )
            assert False, "expected governed_action_not_found"
        except ValueError as exc:
            assert str(exc) == "governed_action_not_found"


def test_override_appears_in_evidence_packet():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _high_risk(s, "A")
        override_service.create_override(
            s, tenant_id="A", governed_action_id=gid, overridden_by="admin",
            reason="pilot need", authority_basis="compliance lead",
            compensating_control="weekly audit",
        )
        packet = evidence_packet.build_action_packet(s, governed_action_id=gid, tenant_id="A")
    assert packet["overrides"]
    assert packet["overrides"][0]["authority_basis"] == "compliance lead"
    assert packet["governed_actions"][0]["status"] == "override_recorded"


# --- endpoint RBAC ---------------------------------------------------------

def test_override_without_authority_fails():
    with _factory()() as s:
        seed_pilot(s)
        gid = governance_workflow.list_runs(s, tenant_id=DEMO_TENANT_ID)[0]["governed_action_id"]

    body = {"reason": "r", "authority_basis": "a", "compensating_control": "c"}
    with TestClient(app) as client:
        # No override authority.
        assert client.post(f"/workflows/runs/{gid}/override", json=body,
                           headers={"X-Api-Key": "pilot-operator-key"}).status_code == 403
        assert client.post(f"/workflows/runs/{gid}/override", json=body,
                           headers={"X-Api-Key": "pilot-reviewer-key"}).status_code == 403
        assert client.post(f"/workflows/runs/{gid}/override", json=body,
                           headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 403
        # Admin holds override_high_risk_action.
        ok = client.post(f"/workflows/runs/{gid}/override", json=body,
                         headers={"X-Api-Key": "pilot-admin-key"})
        assert ok.status_code == 200 and ok.json()["status"] == "override_recorded"
        # Unknown action -> 404.
        assert client.post("/workflows/runs/nope/override", json=body,
                           headers={"X-Api-Key": "pilot-admin-key"}).status_code == 404
