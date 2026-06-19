"""AI Vendor / Automation Governance Review workflow tests (PR 9 / Phase 2).

Covers the end-to-end loop, deterministic risk classification, the medium/high
approval gate, audit recording, the evidence-packet path, RBAC on the workflow
endpoints (Operator submits, Reviewer approves, Auditor views/exports), and
tenant isolation.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from services import (
    approval_service,
    evidence_packet,
    governance_workflow,
    rbac_service,
    risk_service,
    tenant_service,
)
from services.policy_service import PolicyCategory


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


# --- risk classifier (deterministic) --------------------------------------

def test_risk_classifier_is_deterministic_low_medium_high():
    low = risk_service.classify_risk(
        data_sensitivity="internal", external_exposure=False, autonomy_level="assisted",
        policy_category=PolicyCategory.draft_only,
    )
    medium = risk_service.classify_risk(
        data_sensitivity="pii", external_exposure=True, autonomy_level="none",
        policy_category=PolicyCategory.draft_only,
    )
    high = risk_service.classify_risk(
        data_sensitivity="regulated", external_exposure=True, autonomy_level="autonomous",
        policy_category=PolicyCategory.outbound_send,
    )
    assert low.level == "low"
    assert medium.level == "medium"
    assert high.level == "high"
    # Deterministic: same inputs -> same score.
    again = risk_service.classify_risk(
        data_sensitivity="regulated", external_exposure=True, autonomy_level="autonomous",
        policy_category=PolicyCategory.outbound_send,
    )
    assert again.score == high.score


# --- workflow service ------------------------------------------------------

def test_low_risk_run_clears_without_approval():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        run = governance_workflow.submit_vendor_governance_review(
            s, tenant_id="A", actor="op",
            vendor_name="Acme Notes AI", system_type="summarizer",
            intended_use="internal meeting notes",
            data_sensitivity="internal", external_exposure=False, autonomy_level="assisted",
        )
    assert run["risk"]["level"] == "low"
    assert run["requires_approval"] is False
    assert run["status"] == "cleared"
    assert run["approval_id"] is None


def test_high_risk_run_requires_approval_and_records_audit_and_evidence():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        run = governance_workflow.submit_vendor_governance_review(
            s, tenant_id="A", actor="op",
            vendor_name="VendorX Autopilot", system_type="autonomous agent",
            intended_use="customer outreach",
            data_sensitivity="regulated", external_exposure=True, autonomy_level="autonomous",
        )
        gid = run["governed_action_id"]
        assert run["risk"]["level"] == "high"
        assert run["requires_approval"] is True
        assert run["status"] == "pending_approval"
        assert run["approval_id"]

        detail = governance_workflow.get_run(s, governed_action_id=gid, tenant_id="A")
        assert detail["audit_event_count"] >= 3  # submitted + policy + risk (+approval)
        assert detail["evidence_artifact_count"] == 1

        # Evidence packet path reuses the existing service.
        packet = evidence_packet.build_action_packet(s, governed_action_id=gid, tenant_id="A")
        assert packet is not None
        assert packet["packet_type"] == "governed_action"
        assert len(packet["governed_actions"]) == 1
        assert packet["audit_chain_verification"]["status"] == "verified"
        # Packet must surface the workflow step audit events, not just approval ones.
        packet_actions = {e["action"] for e in packet["audit_events"]}
        assert any(a.startswith("governance_review.") for a in packet_actions)
        assert "governance_review.risk_classified" in packet_actions


def test_medium_risk_requires_approval():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        run = governance_workflow.submit_vendor_governance_review(
            s, tenant_id="A", actor="op",
            vendor_name="Dataco", system_type="analytics",
            intended_use="reporting",
            data_sensitivity="pii", external_exposure=True, autonomy_level="none",
        )
    assert run["risk"]["level"] == "medium"
    assert run["requires_approval"] is True
    assert run["approval_id"]


def test_approve_then_run_reports_approved():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        run = governance_workflow.submit_vendor_governance_review(
            s, tenant_id="A", actor="op",
            vendor_name="VendorX", system_type="autonomous agent", intended_use="outreach",
            data_sensitivity="regulated", external_exposure=True, autonomy_level="autonomous",
        )
        approval_service.approve(s, run["approval_id"], actor="reviewer", tenant_id="A")
        detail = governance_workflow.get_run(s, governed_action_id=run["governed_action_id"], tenant_id="A")
    assert detail["status"] == "approved"
    assert detail["approval_status"] == "approved"


def test_packet_reflects_final_decision_not_pending():
    """Evidence packet must render the governed action's status from the final
    approval decision (not the stale submit-time 'pending_approval')."""
    high = dict(
        vendor_name="V", system_type="autonomous agent", intended_use="outreach",
        data_sensitivity="regulated", external_exposure=True, autonomy_level="autonomous",
    )
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        r1 = governance_workflow.submit_vendor_governance_review(s, tenant_id="A", actor="op", **high)
        r2 = governance_workflow.submit_vendor_governance_review(s, tenant_id="A", actor="op", **high)

        # Before any decision the packet shows pending_approval.
        pre = evidence_packet.build_action_packet(s, governed_action_id=r1["governed_action_id"], tenant_id="A")
        assert pre["governed_actions"][0]["status"] == "pending_approval"

        approval_service.approve(s, r1["approval_id"], actor="rev", tenant_id="A")
        approval_service.reject(s, r2["approval_id"], actor="rev", reason="not approved", tenant_id="A")

        p1 = evidence_packet.build_action_packet(s, governed_action_id=r1["governed_action_id"], tenant_id="A")
        p2 = evidence_packet.build_action_packet(s, governed_action_id=r2["governed_action_id"], tenant_id="A")

    assert p1["governed_actions"][0]["status"] == "approved"
    assert p2["governed_actions"][0]["status"] == "rejected"
    assert all(g["status"] != "pending_approval" for g in p1["governed_actions"] + p2["governed_actions"])
    # Audit trail unchanged and still verifiable.
    assert p1["audit_chain_verification"]["status"] == "verified"
    assert p2["audit_chain_verification"]["status"] == "verified"


def test_run_tenant_isolation_service_level():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        run = governance_workflow.submit_vendor_governance_review(
            s, tenant_id="A", actor="op", vendor_name="V", system_type="t", intended_use="u",
            data_sensitivity="internal", external_exposure=False, autonomy_level="assisted",
        )
        gid = run["governed_action_id"]
        assert governance_workflow.get_run(s, governed_action_id=gid, tenant_id="B") is None
        assert governance_workflow.get_run(s, governed_action_id=gid, tenant_id="A") is not None


# --- RBAC + tenant isolation via the API ----------------------------------

def _setup_rbac(session):
    rbac_service.seed_rbac(session)
    session.add(Tenant(id="A", name="A"))
    session.add(Tenant(id="B", name="B"))
    session.commit()
    for role, key in [("Operator", "op-A"), ("Reviewer", "rev-A"), ("Auditor", "aud-A")]:
        u = rbac_service.provision_user(session, tenant_id="A", email=f"{role}@a.test")
        rbac_service.assign_role(session, user_id=u.id, role_name=role, tenant_id="A")
        tenant_service.provision_api_key(session, tenant_id="A", name=role, raw_key=key, user_id=u.id)
    ub = rbac_service.provision_user(session, tenant_id="B", email="aud@b.test")
    rbac_service.assign_role(session, user_id=ub.id, role_name="Auditor", tenant_id="B")
    tenant_service.provision_api_key(session, tenant_id="B", name="Auditor", raw_key="aud-B", user_id=ub.id)


def _submit_body():
    return {
        "vendor_name": "VendorX Autopilot", "system_type": "autonomous agent",
        "intended_use": "customer outreach", "data_sensitivity": "regulated",
        "external_exposure": True, "autonomy_level": "autonomous",
    }


def test_workflow_rbac_and_tenant_isolation_via_api():
    with _factory()() as s:
        _setup_rbac(s)

    with TestClient(app) as client:
        # Operator can submit.
        r = client.post("/workflows/vendor-governance-review", json=_submit_body(),
                        headers={"X-Api-Key": "op-A"})
        assert r.status_code == 200
        gid = r.json()["governed_action_id"]
        approval_id = r.json()["approval_id"]
        assert r.json()["status"] == "pending_approval"

        # Reviewer cannot submit (no create permission).
        assert client.post("/workflows/vendor-governance-review", json=_submit_body(),
                           headers={"X-Api-Key": "rev-A"}).status_code == 403
        # Auditor cannot submit.
        assert client.post("/workflows/vendor-governance-review", json=_submit_body(),
                           headers={"X-Api-Key": "aud-A"}).status_code == 403

        # Reviewer can approve via the existing approvals route.
        assert client.post(f"/approvals/{approval_id}/approve", json={"actor": "rev"},
                           headers={"X-Api-Key": "rev-A"}).status_code == 200

        # Auditor can view the run and export the evidence packet.
        assert client.get(f"/workflows/runs/{gid}", headers={"X-Api-Key": "aud-A"}).status_code == 200
        assert client.get(f"/evidence/packets/export/{gid}?format=json",
                          headers={"X-Api-Key": "aud-A"}).status_code == 200

        # Tenant B cannot see tenant A's run.
        assert client.get(f"/workflows/runs/{gid}", headers={"X-Api-Key": "aud-B"}).status_code == 404
