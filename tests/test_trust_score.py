"""Trust Score v0 tests (PR 18)."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from scripts.seed_pilot import DEMO_TENANT_ID, seed_pilot
from services import governance_workflow, tenant_service, trust_score_service
from services.trust_score_service import band_for, score_packet


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _high_risk(session, tenant):
    return governance_workflow.submit_vendor_governance_review(
        session, tenant_id=tenant, actor="operator", vendor_name="VendorX",
        system_type="autonomous agent", intended_use="outreach", data_sensitivity="regulated",
        external_exposure=True, autonomy_level="autonomous",
    )["governed_action_id"]


def test_band_thresholds():
    assert band_for(100) == "Verified"
    assert band_for(90) == "Verified"
    assert band_for(89) == "Strong"
    assert band_for(60) == "Moderate"
    assert band_for(40) == "Weak"
    assert band_for(39) == "High Risk"
    assert band_for(0) == "High Risk"


def test_score_packet_is_explainable_and_bounded():
    # Minimal synthetic packet: verified chain, no approvals/controls/regs.
    packet = {
        "tenant_id": "A",
        "audit_chain_verification": {"status": "verified", "verified_count": 3, "total_count": 3},
        "approvals": [], "mapped_controls": [], "mapped_regulations": [],
        "evidence_gaps": ["missing_control_mappings"], "overrides": [],
        "policy_decisions": [], "audit_events": [],
    }
    result = score_packet(packet, app_env="production")
    assert 0 <= result["score"] <= 100
    assert result["score_band"] == band_for(result["score"])
    # Every dimension is present with points/max/reasons -> no black box.
    assert len(result["breakdown"]) == 10
    for d in result["breakdown"]:
        assert set(d) >= {"dimension", "label", "points", "max_points", "reasons"}
        assert 0 <= d["points"] <= d["max_points"]
        assert d["reasons"]
    assert sum(d["max_points"] for d in result["breakdown"]) == 100
    # Audit integrity earned full; control coverage earned zero (explained).
    by = {d["dimension"]: d for d in result["breakdown"]}
    assert by["audit_integrity"]["points"] == by["audit_integrity"]["max_points"]
    assert by["control_coverage"]["points"] == 0


def test_demo_vs_production_rbac_dimension():
    packet = {"tenant_id": "A", "audit_chain_verification": {"status": "verified", "verified_count": 1, "total_count": 1},
              "approvals": [], "mapped_controls": [], "mapped_regulations": [], "evidence_gaps": [],
              "overrides": [], "policy_decisions": [], "audit_events": []}
    prod = score_packet(packet, app_env="production")["score"]
    demo = score_packet(packet, app_env="demo")["score"]
    assert prod > demo  # hardened RBAC scores higher


def test_score_action_persists_versioned():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.commit()
        gid = _high_risk(s, "A")
        r1 = trust_score_service.score_action(s, governed_action_id=gid, tenant_id="A")
        r2 = trust_score_service.score_action(s, governed_action_id=gid, tenant_id="A")
        assert r1["scope_type"] == "governed_action"
        assert r1["version"] == 1 and r2["version"] == 2  # new version each compute
        assert 0 <= r1["score"] <= 100
        latest = trust_score_service.get_latest(s, scope_type="governed_action", scope_id=gid, tenant_id="A")
        assert latest.version == 2


def test_score_action_tenant_isolation():
    with _factory()() as s:
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        gid = _high_risk(s, "A")
        assert trust_score_service.score_action(s, governed_action_id=gid, tenant_id="B") is None
        assert trust_score_service.score_action(s, governed_action_id=gid, tenant_id="A") is not None


def test_trust_endpoints_rbac_and_shape():
    with _factory()() as s:
        seed_pilot(s)
        gid = governance_workflow.list_runs(s, tenant_id=DEMO_TENANT_ID)[0]["governed_action_id"]
        tenant_service.provision_api_key(s, tenant_id=DEMO_TENANT_ID, name="nouser", raw_key="nouser-trust")

    with TestClient(app) as client:
        # Auditor (view_audit) can read; response carries an explainable breakdown.
        r = client.get(f"/trust/score/{gid}", headers={"X-Api-Key": "pilot-auditor-key"})
        assert r.status_code == 200
        body = r.json()
        assert body["score_band"] == band_for(body["score"])
        assert len(body["breakdown"]) == 10
        # Tenant + workflow scopes resolve.
        assert client.get(f"/trust/tenant/{DEMO_TENANT_ID}", headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 200
        # No view_audit -> 403.
        assert client.get(f"/trust/score/{gid}", headers={"X-Api-Key": "nouser-trust"}).status_code == 403
        # Unknown action -> 404.
        assert client.get("/trust/score/nope", headers={"X-Api-Key": "pilot-auditor-key"}).status_code == 404
