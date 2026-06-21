"""Persisted evidence packet tests (PR 14)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, seed_pilot
from services import (
    audit_service,
    evidence_packet,
    evidence_store,
    governance_workflow,
)


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _build_run(session, tenant: str) -> str:
    run = governance_workflow.submit_vendor_governance_review(
        session, tenant_id=tenant, actor="op", vendor_name="V", system_type="t",
        intended_use="u", data_sensitivity="regulated", external_exposure=True,
        autonomy_level="autonomous",
    )
    return run["governed_action_id"]


# --- service: persist, version, hash, audit ---------------------------------

def test_persist_versions_and_hashes_and_supersedes():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _build_run(s, "A")
        packet = evidence_packet.build_action_packet(s, governed_action_id=gid, tenant_id="A")

        p1 = evidence_store.persist_packet(s, tenant_id="A", packet=packet, generated_by="auditor")
        assert p1.version == 1
        assert p1.packet_hash and len(p1.packet_hash) == 64
        assert p1.retention_status == "active"

        p2 = evidence_store.persist_packet(s, tenant_id="A", packet=packet, generated_by="auditor")
        assert p2.version == 2 and p2.retention_status == "active"

        # First version superseded; retrievable by id.
        refreshed = evidence_store.get_packet(s, p1.id, tenant_id="A")
        assert refreshed.retention_status == "superseded"

        # Generation recorded an audit event on the packet.
        events = audit_service.list_for_resource(
            s, resource_type="evidence_packet", resource_id=p2.id, tenant_id="A"
        )
        assert any(e.action == "evidence.packet.generated" for e in events)


def test_download_records_audit_event():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _build_run(s, "A")
        packet = evidence_packet.build_action_packet(s, governed_action_id=gid, tenant_id="A")
        row = evidence_store.persist_packet(s, tenant_id="A", packet=packet, generated_by="auditor")
        evidence_store.record_download(s, packet=row, fmt="md", tenant_id="A", downloaded_by="auditor")
        events = audit_service.list_for_resource(
            s, resource_type="evidence_packet", resource_id=row.id, tenant_id="A"
        )
        downloads = [e for e in events if e.action == "evidence.packet.downloaded"]
    assert downloads


def test_persist_tenant_isolation():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        gid = _build_run(s, "A")
        packet = evidence_packet.build_action_packet(s, governed_action_id=gid, tenant_id="A")
        row = evidence_store.persist_packet(s, tenant_id="A", packet=packet, generated_by="op")
        assert evidence_store.get_packet(s, row.id, tenant_id="B") is None
        assert evidence_store.get_packet(s, row.id, tenant_id="A") is not None


# --- endpoints: RBAC + retrieval --------------------------------------------

def test_persist_endpoints_rbac_and_retrieval():
    with _factory()() as s:
        seed_pilot(s)
        gid = governance_workflow.list_runs(s, tenant_id=DEMO_TENANT_ID)[0]["governed_action_id"]

    with TestClient(app) as client:
        # Operator lacks export_evidence -> cannot persist.
        assert client.post(f"/evidence/packets/action/{gid}/persist",
                           headers={"X-Api-Key": "pilot-operator-key"}).status_code == 403
        # Auditor has export_evidence -> persists.
        r = client.post(f"/evidence/packets/action/{gid}/persist",
                        headers={"X-Api-Key": "pilot-auditor-key"})
        assert r.status_code == 200
        pid = r.json()["id"]
        assert r.json()["version"] == 1 and r.json()["packet_hash"]

        # Retrieve + list (view_audit).
        assert client.get(f"/evidence/packets/{pid}", headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 200
        lst = client.get("/evidence/packets", headers={"X-Api-Key": "pilot-auditor-key"})
        assert lst.status_code == 200 and any(p["id"] == pid for p in lst.json()["items"])

        # Download stored packet (records audit).
        assert client.get(f"/evidence/packets/{pid}/download?format=md",
                          headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 200
        # Unknown id -> 404.
        assert client.get("/evidence/packets/does-not-exist",
                          headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 404
