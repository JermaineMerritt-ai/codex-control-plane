"""Control/regulation catalog + mapping tests (PR 5).

Covers idempotent seeding, framework/control/regulation retrieval, governed-
action <-> control mapping integrity (uniqueness + tenant scoping), the read
endpoints, and procurement-safe language.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import GovernedAction, Tenant
from db.session import get_engine
from services import control_catalog

EXPECTED_FRAMEWORKS = 14
EXPECTED_REGULATIONS = 6


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _nist_ai_rmf(session):
    return next(f for f in control_catalog.list_frameworks(session) if f.name == "NIST AI RMF")


def test_seed_is_idempotent():
    with _factory()() as s:
        control_catalog.seed_control_catalog(s)
        control_catalog.seed_control_catalog(s)  # second call must not duplicate
        frameworks = control_catalog.list_frameworks(s)
        regs = control_catalog.list_regulations(s)
        total_controls = sum(len(control_catalog.list_controls(s, f.id)) for f in frameworks)
    assert len(frameworks) == EXPECTED_FRAMEWORKS
    assert len(regs) == EXPECTED_REGULATIONS
    assert total_controls == sum(len(v) for v in control_catalog.FRAMEWORK_CONTROLS.values())


def test_framework_and_control_retrieval():
    with _factory()() as s:
        control_catalog.seed_control_catalog(s)
        fw = _nist_ai_rmf(s)
        codes = {c.code for c in control_catalog.list_controls(s, fw.id)}
    assert codes == {"GOVERN", "MAP", "MEASURE", "MANAGE"}


def test_mapping_integrity_uniqueness_and_tenant_scope():
    with _factory()() as s:
        control_catalog.seed_control_catalog(s)
        s.add(Tenant(id="A", name="A"))
        s.add(Tenant(id="B", name="B"))
        s.commit()
        cid = control_catalog.list_controls(s, _nist_ai_rmf(s).id)[0].id

        ga_a = GovernedAction(tenant_id="A", action_type="email.send", status="pending")
        ga_b = GovernedAction(tenant_id="B", action_type="email.send", status="pending")
        s.add(ga_a)
        s.add(ga_b)
        s.commit()
        aid, bid = ga_a.id, ga_b.id

        m = control_catalog.create_action_control_mapping(
            s, tenant_id="A", governed_action_id=aid, control_id=cid, rationale="x"
        )
        assert m.id

        # Duplicate (same tenant, action, control) violates the unique constraint.
        with pytest.raises(IntegrityError):
            control_catalog.create_action_control_mapping(
                s, tenant_id="A", governed_action_id=aid, control_id=cid
            )
        s.rollback()

        # A different tenant's action may map the same control (no collision).
        control_catalog.create_action_control_mapping(
            s, tenant_id="B", governed_action_id=bid, control_id=cid
        )

        assert len(control_catalog.list_action_control_mappings(s, governed_action_id=aid, tenant_id="A")) == 1
        # Tenant B cannot see tenant A's action mappings.
        assert control_catalog.list_action_control_mappings(s, governed_action_id=aid, tenant_id="B") == []


def test_catalog_read_endpoints():
    with TestClient(app) as client:
        fr = client.get("/controls/frameworks")
        assert fr.status_code == 200
        assert len(fr.json()["items"]) == EXPECTED_FRAMEWORKS

        fid = fr.json()["items"][0]["id"]
        cr = client.get(f"/controls/frameworks/{fid}/controls")
        assert cr.status_code == 200 and len(cr.json()["items"]) >= 1

        rg = client.get("/controls/regulations")
        assert rg.status_code == 200 and len(rg.json()["items"]) == EXPECTED_REGULATIONS

        assert client.get("/controls/frameworks/nope/controls").status_code == 404


def test_catalog_language_is_procurement_safe():
    forbidden = ("guarantees compliance", "certifies compliance", "fully compliant")
    with _factory()() as s:
        control_catalog.seed_control_catalog(s)
        descriptions = [f.description or "" for f in control_catalog.list_frameworks(s)]
    assert descriptions
    assert all(d == control_catalog.CATALOG_LANGUAGE for d in descriptions)
    blob = " ".join(descriptions).lower()
    assert not any(phrase in blob for phrase in forbidden)
