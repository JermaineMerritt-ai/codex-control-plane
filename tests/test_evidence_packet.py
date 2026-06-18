"""Evidence packet export tests (PR 7).

Covers packet contents, evidence-gap detection (including broken audit chain),
JSON + Markdown export, tenant isolation, RBAC gating on the endpoints, and
procurement-safe language.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from services import (
    approval_service,
    control_catalog,
    evidence_graph,
    evidence_packet,
    job_service,
    rbac_service,
    tenant_service,
)
from services.job_types import CHAT_ORCHESTRATE, EMAIL_SEND_APPROVED

FORBIDDEN = ("guarantees compliance", "certifies compliance", "fully compliant",
             "guaranteed compliance", "compliance certification", "regulatory approval")


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _build_full_chain(session, tenant: str):
    ai = evidence_graph.create_ai_system(session, tenant_id=tenant, name=f"ai-{tenant}")
    wf = evidence_graph.create_workflow(session, tenant_id=tenant, name=f"wf-{tenant}", ai_system_id=ai.id)
    source_job = job_service.create_job(session, job_type=CHAT_ORCHESTRATE, tenant_id=tenant, payload={})
    appr = approval_service.create_request(
        session, kind="job.gate", tenant_id=tenant, job_id=source_job.id, payload={}
    )
    approval_service.approve(session, appr.id, actor="op", tenant_id=tenant)
    exec_job = job_service.create_job(
        session, job_type=EMAIL_SEND_APPROVED, tenant_id=tenant, payload={"approval_id": appr.id}
    )
    action = evidence_graph.create_governed_action(
        session, tenant_id=tenant, action_type="email.send", workflow_id=wf.id,
        source_job_id=source_job.id, approval_id=appr.id, execution_job_id=exec_job.id,
        policy_version="v1", policy_decision="requires_approval", status="executed",
    )
    control_catalog.seed_control_catalog(session)
    fw = next(f for f in control_catalog.list_frameworks(session) if f.name == "NIST AI RMF")
    control = control_catalog.list_controls(session, fw.id)[0]
    regulation = control_catalog.list_regulations(session)[0]
    control_catalog.create_action_control_mapping(
        session, tenant_id=tenant, governed_action_id=action.id,
        control_id=control.id, regulation_id=regulation.id, rationale="linked",
    )
    evidence_graph.record_evidence_artifact(
        session, tenant_id=tenant, governed_action_id=action.id,
        artifact_type="approval_record", uri="mem://evidence/x",
    )
    return wf, action


def test_action_packet_complete_chain_has_no_gaps():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        _, action = _build_full_chain(s, "A")
        packet = evidence_packet.build_action_packet(s, governed_action_id=action.id, tenant_id="A")

    assert packet is not None
    assert packet["packet_type"] == "governed_action"
    assert len(packet["governed_actions"]) == 1
    assert len(packet["approvals"]) == 1
    assert packet["policy_decisions"][0]["decision"] == "requires_approval"
    assert packet["audit_chain_verification"]["status"] == "verified"
    assert len(packet["mapped_controls"]) >= 1
    assert len(packet["mapped_regulations"]) >= 1
    assert len(packet["evidence_artifacts"]) == 1
    assert packet["evidence_gaps"] == []
    assert packet["generated_at"]
    assert packet["executive_summary"]


def test_action_packet_reports_evidence_gaps():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        bare = evidence_graph.create_governed_action(s, tenant_id="A", action_type="email.send")
        packet = evidence_packet.build_action_packet(s, governed_action_id=bare.id, tenant_id="A")

    gaps = set(packet["evidence_gaps"])
    assert {"missing_approval", "missing_control_mappings", "missing_evidence_artifacts", "missing_audit_records"} <= gaps


def test_broken_audit_chain_is_reported_as_gap():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        _, action = _build_full_chain(s, "A")
        aid = action.id
        # Tamper an audit event for tenant A so self-hash verification fails.
        s.execute(text("UPDATE audit_events SET reason = :r WHERE tenant_id = :t"),
                  {"r": "tampered", "t": "A"})
        s.commit()
        packet = evidence_packet.build_action_packet(s, governed_action_id=aid, tenant_id="A")

    assert packet["audit_chain_verification"]["status"] == "failed"
    assert "broken_audit_chain" in packet["evidence_gaps"]


def test_workflow_and_tenant_packets():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        wf, _ = _build_full_chain(s, "A")
        # second action in the same workflow
        evidence_graph.create_governed_action(s, tenant_id="A", action_type="email.send", workflow_id=wf.id)
        wf_packet = evidence_packet.build_workflow_packet(s, workflow_id=wf.id, tenant_id="A")
        tenant_packet = evidence_packet.build_tenant_packet(s, tenant_id="A")

    assert wf_packet["packet_type"] == "workflow"
    assert len(wf_packet["governed_actions"]) == 2
    assert tenant_packet["packet_type"] == "tenant"
    assert len(tenant_packet["governed_actions"]) == 2


def test_json_and_markdown_export():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        _, action = _build_full_chain(s, "A")
        packet = evidence_packet.build_action_packet(s, governed_action_id=action.id, tenant_id="A")

    parsed = json.loads(evidence_packet.render_json(packet))
    assert parsed["scope_id"] == action.id

    md = evidence_packet.render_markdown(packet)
    assert md.startswith("# Evidence Packet")
    assert "Executive summary" in md and "Evidence gaps" in md
    blob = (md + " " + evidence_packet.render_json(packet)).lower()
    assert not any(phrase in blob for phrase in FORBIDDEN)


def test_packet_tenant_isolation_service_level():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        _, action = _build_full_chain(s, "A")
        assert evidence_packet.build_action_packet(s, governed_action_id=action.id, tenant_id="B") is None
        assert evidence_packet.build_action_packet(s, governed_action_id=action.id, tenant_id="A") is not None


def _setup_rbac(session):
    rbac_service.seed_rbac(session)
    session.add(Tenant(id="A", name="A"))
    session.add(Tenant(id="B", name="B"))
    session.commit()
    ua = rbac_service.provision_user(session, tenant_id="A", email="a@a.test")
    rbac_service.assign_role(session, user_id=ua.id, role_name="Auditor", tenant_id="A")
    tenant_service.provision_api_key(session, tenant_id="A", name="k", raw_key="aud-A", user_id=ua.id)
    ub = rbac_service.provision_user(session, tenant_id="B", email="b@b.test")
    rbac_service.assign_role(session, user_id=ub.id, role_name="Auditor", tenant_id="B")
    tenant_service.provision_api_key(session, tenant_id="B", name="k", raw_key="aud-B", user_id=ub.id)
    tenant_service.provision_api_key(session, tenant_id="A", name="nouser", raw_key="nouser-A")


def test_packet_endpoints_rbac_and_tenant_scope():
    with _factory()() as s:
        _setup_rbac(s)
        _, action = _build_full_chain(s, "A")
        aid = action.id

    with TestClient(app) as client:
        # Auditor in A can read A's packet.
        ok = client.get(f"/evidence/packets/action/{aid}", headers={"X-Api-Key": "aud-A"})
        assert ok.status_code == 200
        assert ok.json()["scope_id"] == aid

        # Cross-tenant -> 404 (never expose another tenant's packet).
        assert client.get(f"/evidence/packets/action/{aid}", headers={"X-Api-Key": "aud-B"}).status_code == 404
        # No view_audit -> 403 (never bypass RBAC).
        assert client.get(f"/evidence/packets/action/{aid}", headers={"X-Api-Key": "nouser-A"}).status_code == 403
        # Operator bypass works.
        assert client.get(f"/evidence/packets/action/{aid}").status_code == 200

        # Export formats.
        md = client.get(f"/evidence/packets/export/{aid}?format=md", headers={"X-Api-Key": "aud-A"})
        assert md.status_code == 200 and md.text.startswith("# Evidence Packet")
        js = client.get(f"/evidence/packets/export/{aid}?format=json", headers={"X-Api-Key": "aud-A"})
        assert js.status_code == 200 and js.json()["scope_id"] == aid
