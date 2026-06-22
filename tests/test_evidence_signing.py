"""Signed evidence packet tests (PR 20)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, seed_pilot
from services import (
    evidence_packet,
    evidence_signature_service,
    evidence_store,
    governance_workflow,
    rbac_service,
    tenant_service,
)


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _persisted_packet(session, tenant):
    gid = governance_workflow.submit_vendor_governance_review(
        session, tenant_id=tenant, actor="operator", vendor_name="VendorX",
        system_type="autonomous agent", intended_use="outreach", data_sensitivity="regulated",
        external_exposure=True, autonomy_level="autonomous",
    )["governed_action_id"]
    packet = evidence_packet.build_action_packet(session, governed_action_id=gid, tenant_id=tenant)
    return evidence_store.persist_packet(session, tenant_id=tenant, packet=packet, generated_by="auditor")


def test_persisted_packet_is_signed_and_valid():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        row = _persisted_packet(s, "A")
        assert row.packet_signature and row.signature_algorithm == "Ed25519"
        assert row.signed_at is not None and row.expires_at is not None
        result = evidence_signature_service.verify_packet(row)
    assert result["status"] == "valid"
    assert result["public_key"]  # published for independent verification
    assert result["reasons"]


def test_tampered_content_detected():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        row = _persisted_packet(s, "A")
        # Mutate the stored export after signing -> recomputed hash won't match.
        row.json_export = (row.json_export or "{}").replace("}", ', "injected": true}', 1)
        s.add(row)
        s.commit()
        result = evidence_signature_service.verify_packet(row)
    assert result["status"] == "tampered"


def test_tampered_hash_swap_detected():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        row = _persisted_packet(s, "A")
        row.packet_hash = "0" * 64  # swap the hash the signature commits to
        s.add(row)
        s.commit()
        result = evidence_signature_service.verify_packet(row)
    assert result["status"] == "tampered"


def test_expired_packet():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        row = _persisted_packet(s, "A")
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        s.add(row)
        s.commit()
        result = evidence_signature_service.verify_packet(row)
    assert result["status"] == "expired"


def test_revoked_packet():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        row = _persisted_packet(s, "A")
        evidence_signature_service.revoke_packet(s, packet=row, reason="superseded by v2", revoked_by="admin")
        result = evidence_signature_service.verify_packet(row)
    assert result["status"] == "revoked"
    assert "superseded by v2" in result["reasons"][0]


def test_verify_endpoint_rbac_tenant_and_states():
    with _factory()() as s:
        seed_pilot(s)
        gid = governance_workflow.list_runs(s, tenant_id=DEMO_TENANT_ID)[0]["governed_action_id"]
        packet = evidence_packet.build_action_packet(s, governed_action_id=gid, tenant_id=DEMO_TENANT_ID)
        row = evidence_store.persist_packet(s, tenant_id=DEMO_TENANT_ID, packet=packet, generated_by="auditor")
        pid = row.id
        # A second tenant with its OWN auditor (has view_audit) -> proves the 404 is
        # tenant isolation, not a missing permission.
        s.add(Tenant(id="OTHER", name="Other"))
        s.commit()
        other_user = rbac_service.provision_user(s, tenant_id="OTHER", email="aud@other.test")
        rbac_service.assign_role(s, user_id=other_user.id, role_name="Auditor", tenant_id="OTHER")
        tenant_service.provision_api_key(s, tenant_id="OTHER", name="other-aud", raw_key="other-key", user_id=other_user.id)
        tenant_service.provision_api_key(s, tenant_id=DEMO_TENANT_ID, name="nouser", raw_key="nouser-sign")

    AUD = {"X-Api-Key": "pilot-auditor-key"}
    with TestClient(app) as client:
        # Valid verification, with public key.
        r = client.get(f"/evidence/verify/{pid}", headers=AUD)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "valid" and body["public_key"]
        # Cross-tenant -> 404 (isolation, non-leaking).
        assert client.get(f"/evidence/verify/{pid}", headers={"X-Api-Key": "other-key"}).status_code == 404
        # Unknown packet -> 404 not_found.
        assert client.get("/evidence/verify/nope", headers=AUD).status_code == 404
        # No view_audit -> 403.
        assert client.get(f"/evidence/verify/{pid}", headers={"X-Api-Key": "nouser-sign"}).status_code == 403
        # Revoke via API (export_evidence), then verify reports revoked.
        rev = client.post(f"/evidence/packets/{pid}/revoke", headers=AUD, json={"reason": "test revoke"})
        assert rev.status_code == 200
        assert client.get(f"/evidence/verify/{pid}", headers=AUD).json()["status"] == "revoked"
        # Operator lacks export_evidence -> cannot revoke.
        assert client.post(f"/evidence/packets/{pid}/revoke", headers={"X-Api-Key": "pilot-operator-key"},
                           json={"reason": "x"}).status_code == 403
