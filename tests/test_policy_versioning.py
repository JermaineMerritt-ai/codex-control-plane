"""Policy versioning tests (PR 15).

Proves: governed actions bind to the exact active policy version; a new version
supersedes the prior one; OLD actions remain tied to their original version;
rollback = activate a previous version (forward-only, no rewrite of history);
RBAC on lifecycle ops; the evidence packet surfaces the bound version.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, seed_pilot
from services import evidence_graph, evidence_packet, governance_workflow, policy_version_service as pv


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _submit(session, tenant):
    run = governance_workflow.submit_vendor_governance_review(
        session, tenant_id=tenant, actor="op", vendor_name="V", system_type="t",
        intended_use="u", data_sensitivity="regulated", external_exposure=True,
        autonomy_level="autonomous",
    )
    return run["governed_action_id"]


def test_action_binds_to_active_version_and_old_actions_stay_bound():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        v1 = pv.create_version(s, tenant_id="A", version="v1")
        pv.activate(s, version_id=v1.id, tenant_id="A")

        a1 = _submit(s, "A")
        assert evidence_graph.get_governed_action(s, a1, tenant_id="A").policy_version_id == v1.id

        v2 = pv.create_version(s, tenant_id="A", version="v2", change_reason="tightened")
        pv.activate(s, version_id=v2.id, tenant_id="A")
        assert pv.get_version(s, v1.id).status == "superseded"

        a2 = _submit(s, "A")
        assert evidence_graph.get_governed_action(s, a2, tenant_id="A").policy_version_id == v2.id
        # Old action still bound to v1 (immutable).
        assert evidence_graph.get_governed_action(s, a1, tenant_id="A").policy_version_id == v1.id


def test_rollback_activates_previous_version_without_rewriting_history():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        v1 = pv.create_version(s, tenant_id="A", version="v1")
        pv.activate(s, version_id=v1.id, tenant_id="A")
        v2 = pv.create_version(s, tenant_id="A", version="v2")
        pv.activate(s, version_id=v2.id, tenant_id="A")
        a_v2 = _submit(s, "A")  # bound to v2

        # Roll back = activate previous (v1); supersede v2. No history rewrite.
        pv.rollback_to(s, version_id=v1.id, change_reason="regression in v2", tenant_id="A")
        assert pv.get_version(s, v1.id).status == "active"
        assert pv.get_version(s, v2.id).status == "superseded"

        a_v1 = _submit(s, "A")  # new actions bind v1 again
        assert evidence_graph.get_governed_action(s, a_v1, tenant_id="A").policy_version_id == v1.id
        # The v2-era action is untouched.
        assert evidence_graph.get_governed_action(s, a_v2, tenant_id="A").policy_version_id == v2.id


def test_system_default_used_when_tenant_has_no_policy():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        default = pv.seed_default_policy(s)  # system default (tenant None), active
        a = _submit(s, "A")
        assert evidence_graph.get_governed_action(s, a, tenant_id="A").policy_version_id == default.id


def test_packet_surfaces_policy_version_id():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        v1 = pv.create_version(s, tenant_id="A", version="v1")
        pv.activate(s, version_id=v1.id, tenant_id="A")
        v1_id = v1.id  # capture before the session closes
        gid = _submit(s, "A")
        packet = evidence_packet.build_action_packet(s, governed_action_id=gid, tenant_id="A")
    assert packet["policy_decisions"][0]["policy_version_id"] == v1_id


def test_policy_lifecycle_rbac_via_api():
    with _factory()() as s:
        seed_pilot(s)

    with TestClient(app) as client:
        body = {"version": "v2", "change_reason": "tighten controls"}
        # Operator/Auditor lack manage_policies.
        assert client.post("/policies", json=body, headers={"X-Api-Key": "pilot-operator-key"}).status_code == 403
        assert client.post("/policies", json=body, headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 403
        # Admin can create + activate.
        created = client.post("/policies", json=body, headers={"X-Api-Key": "pilot-admin-key"})
        assert created.status_code == 200
        pid = created.json()["id"]
        assert client.post(f"/policies/{pid}/activate", headers={"X-Api-Key": "pilot-admin-key"}).status_code == 200
        # Auditor can read (view_audit).
        assert client.get("/policies", headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 200
        # Rollback gated by manage_policies.
        assert client.post(f"/policies/{pid}/rollback", json={"change_reason": "x"},
                           headers={"X-Api-Key": "pilot-operator-key"}).status_code == 403
        assert client.post(f"/policies/{pid}/rollback", json={"change_reason": "x"},
                           headers={"X-Api-Key": "pilot-admin-key"}).status_code == 200
