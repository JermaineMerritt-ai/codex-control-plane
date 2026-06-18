"""Evidence graph foundation tests (PR 6).

Covers full-chain assembly (AI System → Workflow → Governed Action → Policy
Decision → Approval → Execution → Audit Event → Control Mapping → Regulation →
Evidence Artifact), tenant isolation, and the tenant-scoped + RBAC-gated read
endpoints.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from services import (
    approval_service,
    control_catalog,
    evidence_graph,
    job_service,
    rbac_service,
    tenant_service,
)
from services.job_types import CHAT_ORCHESTRATE, EMAIL_SEND_APPROVED


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _build_chain(session, tenant: str):
    """Create a complete governance chain for one governed action."""
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
    return action


def test_graph_assembles_full_chain():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        action = _build_chain(s, "A")
        graph = evidence_graph.get_evidence_graph(s, governed_action_id=action.id, tenant_id="A")

    assert graph is not None
    assert graph["ai_system"] is not None
    assert graph["workflow"] is not None
    assert graph["approval"] is not None
    assert graph["execution_job"] is not None
    assert graph["policy_decision"]["decision"] == "requires_approval"
    # Audit linkage: approval.created + approval.approved both key off the approval id.
    assert len(graph["audit_events"]) >= 2
    # Control + regulation linkage.
    assert len(graph["control_mappings"]) == 1
    assert graph["control_mappings"][0]["control"] is not None
    assert graph["control_mappings"][0]["framework"] is not None
    assert graph["control_mappings"][0]["regulation"] is not None
    # Evidence artifact linkage.
    assert len(graph["evidence_artifacts"]) == 1


def test_graph_tenant_isolation():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        gid = _build_chain(s, "A").id

        assert evidence_graph.get_evidence_graph(s, governed_action_id=gid, tenant_id="B") is None
        assert evidence_graph.get_evidence_graph(s, governed_action_id=gid, tenant_id="A") is not None

        a_actions = {a.id for a in evidence_graph.list_governed_actions(s, tenant_id="A")}
        b_actions = {a.id for a in evidence_graph.list_governed_actions(s, tenant_id="B")}
        assert gid in a_actions and gid not in b_actions

        assert evidence_graph.list_ai_systems(s, tenant_id="B") == []
        assert evidence_graph.list_evidence_artifacts(s, tenant_id="B") == []
        assert all(a.tenant_id == "A" for a in evidence_graph.list_ai_systems(s, tenant_id="A"))


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


def test_evidence_endpoints_tenant_scoped_and_gated():
    with _factory()() as s:
        _setup_rbac(s)
        gid = _build_chain(s, "A").id

    with TestClient(app) as client:
        # Auditor (view_audit) in tenant A reads A's graph.
        ok = client.get(f"/evidence/actions/{gid}/graph", headers={"X-Api-Key": "aud-A"})
        assert ok.status_code == 200
        body = ok.json()
        assert body["governed_action_id"] == gid
        assert len(body["control_mappings"]) == 1
        assert body["ai_system"] is not None

        # Auditor in tenant B cannot see A's action -> 404 (non-leaking).
        assert client.get(f"/evidence/actions/{gid}/graph", headers={"X-Api-Key": "aud-B"}).status_code == 404
        # User-less key lacks view_audit -> 403.
        assert client.get(f"/evidence/actions/{gid}/graph", headers={"X-Api-Key": "nouser-A"}).status_code == 403
        # Operator bypass (no key) works.
        assert client.get(f"/evidence/actions/{gid}/graph").status_code == 200


def test_evidence_list_endpoints():
    with _factory()() as s:
        _setup_rbac(s)
        _build_chain(s, "A")
    with TestClient(app) as client:
        actions = client.get("/evidence/actions", headers={"X-Api-Key": "aud-A"})
        assert actions.status_code == 200 and len(actions.json()["items"]) == 1
        systems = client.get("/evidence/ai-systems", headers={"X-Api-Key": "aud-A"})
        assert systems.status_code == 200 and len(systems.json()["items"]) == 1
        # Tenant B sees none of A's graph nodes.
        assert client.get("/evidence/actions", headers={"X-Api-Key": "aud-B"}).json()["items"] == []
