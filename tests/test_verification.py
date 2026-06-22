"""Procurement verification lifecycle tests (PR 21)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, seed_pilot
from services import (
    approval_service,
    evidence_packet,
    evidence_signature_service,
    evidence_store,
    governance_workflow,
    rbac_service,
    tenant_service,
    verification_service,
)


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _approved_action_with_signed_packet(session, tenant):
    """A high-risk action, approved, with a persisted (auto-signed) evidence packet."""
    run = governance_workflow.submit_vendor_governance_review(
        session, tenant_id=tenant, actor="operator", vendor_name="VendorX",
        system_type="autonomous agent", intended_use="lending", data_sensitivity="regulated",
        external_exposure=True, autonomy_level="autonomous",
    )
    gid = run["governed_action_id"]
    approval_id = run.get("approval_id")
    if not approval_id:
        approval_id = approval_service.list_approvals(session, status="pending", tenant_id=tenant)[0].id
    approval_service.approve(session, approval_id, actor="reviewer", note="ok", tenant_id=tenant)
    packet = evidence_packet.build_action_packet(session, governed_action_id=gid, tenant_id=tenant)
    evidence_store.persist_packet(session, tenant_id=tenant, packet=packet, generated_by="auditor")
    return gid


def test_request_requires_signed_evidence():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        # Action with no persisted packet -> request refuses.
        run = governance_workflow.submit_vendor_governance_review(
            s, tenant_id="A", actor="op", vendor_name="V", system_type="agent",
            intended_use="x", data_sensitivity="regulated", external_exposure=True,
            autonomy_level="autonomous",
        )
        with pytest.raises(ValueError, match="no_signed_evidence"):
            verification_service.request_verification(
                s, tenant_id="A", subject_id=run["governed_action_id"], requested_by="op")
        # Unknown subject -> not found.
        with pytest.raises(ValueError, match="subject_not_found"):
            verification_service.request_verification(s, tenant_id="A", subject_id="nope", requested_by="op")


def test_full_happy_path_request_review_approve_revoke():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _approved_action_with_signed_packet(s, "A")
        v = verification_service.request_verification(s, tenant_id="A", subject_id=gid, requested_by="op")
        assert v.status == "requested" and v.evidence_packet_id

        v, ev = verification_service.review_verification(s, verification_id=v.id, tenant_id="A", reviewed_by="rev")
        assert v.status == "under_review" and ev["status"] == "valid"

        v, score = verification_service.approve_verification(s, verification_id=v.id, tenant_id="A", approved_by="adm")
        assert v.status == "approved"
        assert v.trust_score is not None and v.trust_score >= v.min_score_required
        assert v.trust_score_id

        v = verification_service.revoke_verification(
            s, verification_id=v.id, tenant_id="A", revoked_by="adm", reason="vendor contract ended")
        assert v.status == "revoked" and v.decision_reason == "vendor contract ended"


@pytest.mark.parametrize("breakage", ["tampered", "expired", "revoked", "unsigned"])
def test_review_rejects_bad_evidence(breakage):
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _approved_action_with_signed_packet(s, "A")
        v = verification_service.request_verification(s, tenant_id="A", subject_id=gid, requested_by="op")
        # Break the referenced evidence after request, before review.
        packet = evidence_store.get_packet(s, v.evidence_packet_id, tenant_id="A")
        if breakage == "tampered":
            packet.json_export = (packet.json_export or "{}").replace("}", ', "x": 1}', 1)
        elif breakage == "expired":
            packet.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        elif breakage == "revoked":
            evidence_signature_service.revoke_packet(s, packet=packet, reason="r", revoked_by="a")
        elif breakage == "unsigned":
            packet.packet_signature = None
        s.add(packet)
        s.commit()

        v, ev = verification_service.review_verification(s, verification_id=v.id, tenant_id="A", reviewed_by="rev")
        assert v.status == "rejected"
        assert v.decision_reason == f"evidence_{breakage}"
        # A rejected verification cannot be approved.
        with pytest.raises(ValueError, match="invalid_transition"):
            verification_service.approve_verification(s, verification_id=v.id, tenant_id="A", approved_by="adm")


def test_approval_requires_sufficient_trust_score():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _approved_action_with_signed_packet(s, "A")
        # Demand an unreachably high score -> approval blocked.
        v = verification_service.request_verification(
            s, tenant_id="A", subject_id=gid, requested_by="op", min_score_required=99)
        verification_service.review_verification(s, verification_id=v.id, tenant_id="A", reviewed_by="rev")
        with pytest.raises(ValueError, match="insufficient_trust_score"):
            verification_service.approve_verification(s, verification_id=v.id, tenant_id="A", approved_by="adm")


def test_cross_tenant_isolation():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        gid = _approved_action_with_signed_packet(s, "A")
        v = verification_service.request_verification(s, tenant_id="A", subject_id=gid, requested_by="op")
        # Tenant B cannot see A's verification.
        assert verification_service.get_verification(s, v.id, tenant_id="B") is None
        with pytest.raises(ValueError, match="verification_not_found"):
            verification_service.review_verification(s, verification_id=v.id, tenant_id="B", reviewed_by="rev")


def test_verification_endpoints_rbac_and_cross_tenant():
    with _factory()() as s:
        seed_pilot(s)
        gid = _approved_action_with_signed_packet(s, DEMO_TENANT_ID)
        # A second tenant with its own reviewer (has approve_action) for the 404 check.
        s.add(Tenant(id="OTHER", name="Other"))
        s.commit()
        other = rbac_service.provision_user(s, tenant_id="OTHER", email="rev@other.test")
        rbac_service.assign_role(s, user_id=other.id, role_name="Reviewer", tenant_id="OTHER")
        tenant_service.provision_api_key(s, tenant_id="OTHER", name="other-rev", raw_key="other-rev-key", user_id=other.id)

    OP = {"X-Api-Key": "pilot-operator-key"}    # create_governed_action
    REV = {"X-Api-Key": "pilot-reviewer-key"}   # approve_action
    AUD = {"X-Api-Key": "pilot-auditor-key"}    # neither
    with TestClient(app) as client:
        # Requesting needs create_governed_action: auditor -> 403, operator -> 200.
        assert client.post("/verification/request", headers=AUD, json={"subject_id": gid}).status_code == 403
        req = client.post("/verification/request", headers=OP, json={"subject_id": gid})
        assert req.status_code == 200
        vid = req.json()["id"]
        assert req.json()["status"] == "requested"

        # Approving needs approve_action: operator -> 403.
        assert client.post("/verification/approve", headers=OP, json={"verification_id": vid}).status_code == 403

        # Cross-tenant reviewer -> 404 (isolation).
        assert client.post("/verification/review", headers={"X-Api-Key": "other-rev-key"},
                           json={"verification_id": vid}).status_code == 404

        # Reviewer: review -> approve -> revoke.
        rv = client.post("/verification/review", headers=REV, json={"verification_id": vid})
        assert rv.status_code == 200 and rv.json()["status"] == "under_review"
        ap = client.post("/verification/approve", headers=REV, json={"verification_id": vid})
        assert ap.status_code == 200 and ap.json()["status"] == "approved"
        assert ap.json()["trust_score"] >= ap.json()["min_score_required"]
        rk = client.post("/verification/revoke", headers=REV, json={"verification_id": vid, "reason": "done"})
        assert rk.status_code == 200 and rk.json()["status"] == "revoked"
