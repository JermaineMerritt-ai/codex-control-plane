"""RBAC enforcement tests (PR 4).

Proves: a user with the right role can perform a protected action; a user
without the permission gets 403; tenant isolation still blocks cross-tenant
access even when the role has the permission; an API key without a user_id is
denied protected actions; an invalid key gets 401; and the no-key
operator/system path still works (demo preserved).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import Tenant
from db.session import get_engine
from services import approval_service, job_service, rbac_service, tenant_service
from services.job_types import CHAT_ORCHESTRATE


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _new_pending_approval(session, tenant_id: str):
    job = job_service.create_job(
        session, job_type=CHAT_ORCHESTRATE, tenant_id=tenant_id, payload={}
    )
    return approval_service.create_request(
        session, kind="job.gate", tenant_id=tenant_id, job_id=job.id, payload={}
    )


def _setup(session) -> None:
    """Seed roles, two tenants, and three API keys: Admin user, Viewer user,
    and a user-less tenant key."""
    rbac_service.seed_rbac(session)
    session.add(Tenant(id="A", name="A"))
    session.add(Tenant(id="B", name="B"))
    session.commit()

    admin = rbac_service.provision_user(session, tenant_id="A", email="admin@a.test")
    rbac_service.assign_role(session, user_id=admin.id, role_name="Admin", tenant_id="A")
    tenant_service.provision_api_key(
        session, tenant_id="A", name="admin", raw_key="admin-A", user_id=admin.id
    )

    viewer = rbac_service.provision_user(session, tenant_id="A", email="viewer@a.test")
    rbac_service.assign_role(session, user_id=viewer.id, role_name="Viewer", tenant_id="A")
    tenant_service.provision_api_key(
        session, tenant_id="A", name="viewer", raw_key="viewer-A", user_id=viewer.id
    )

    # Tenant-bound key with NO user => no permissions.
    tenant_service.provision_api_key(session, tenant_id="A", name="nouser", raw_key="nouser-A")


def test_user_with_role_can_perform_protected_action():
    with _factory()() as s:
        _setup(s)
        aid = _new_pending_approval(s, "A").id
    with TestClient(app) as client:
        r = client.post(
            f"/approvals/{aid}/approve",
            json={"actor": "admin", "note": "ok"},
            headers={"X-Api-Key": "admin-A"},
        )
    assert r.status_code == 200


def test_user_without_permission_gets_403():
    with _factory()() as s:
        _setup(s)
        aid = _new_pending_approval(s, "A").id
    with TestClient(app) as client:
        r = client.post(
            f"/approvals/{aid}/approve",
            json={"actor": "viewer"},
            headers={"X-Api-Key": "viewer-A"},
        )
    assert r.status_code == 403
    assert r.json()["detail"] == "permission_denied"


def test_tenant_isolation_blocks_even_when_role_has_permission():
    with _factory()() as s:
        _setup(s)
        bid = _new_pending_approval(s, "B").id  # approval lives in tenant B
    with TestClient(app) as client:
        # admin-A holds approve_action but is bound to tenant A.
        r = client.post(
            f"/approvals/{bid}/approve",
            json={"actor": "admin"},
            headers={"X-Api-Key": "admin-A"},
        )
    assert r.status_code == 400
    assert r.json()["detail"] == "approval_not_found"


def test_api_key_without_user_cannot_perform_protected_action():
    with _factory()() as s:
        _setup(s)
        aid = _new_pending_approval(s, "A").id
    with TestClient(app) as client:
        r = client.post(
            f"/approvals/{aid}/approve",
            json={"actor": "x"},
            headers={"X-Api-Key": "nouser-A"},
        )
    assert r.status_code == 403


def test_invalid_api_key_gets_401():
    with _factory()() as s:
        _setup(s)
        aid = _new_pending_approval(s, "A").id
    with TestClient(app) as client:
        r = client.post(
            f"/approvals/{aid}/approve",
            json={"actor": "x"},
            headers={"X-Api-Key": "bogus-key"},
        )
    assert r.status_code == 401


def test_no_api_key_operator_bypass_preserves_demo():
    with _factory()() as s:
        _setup(s)
        aid = _new_pending_approval(s, "A").id
    with TestClient(app) as client:
        r = client.post(f"/approvals/{aid}/approve", json={"actor": "op"})  # no key
    assert r.status_code == 200


def test_audit_read_requires_view_audit_permission():
    with _factory()() as s:
        _setup(s)
    with TestClient(app) as client:
        # Viewer has view_audit.
        assert client.get("/audit", headers={"X-Api-Key": "viewer-A"}).status_code == 200
        # User-less tenant key has no permissions.
        assert client.get("/audit", headers={"X-Api-Key": "nouser-A"}).status_code == 403
        # Operator bypass (no key) still works.
        assert client.get("/audit").status_code == 200


def test_retry_requires_execute_permission_before_lookup():
    with _factory()() as s:
        _setup(s)
    with TestClient(app) as client:
        # Viewer lacks execute_approved_action -> denied before any job lookup.
        r = client.post("/jobs/does-not-exist/retry", headers={"X-Api-Key": "viewer-A"})
    assert r.status_code == 403


def test_resolve_principal_matrix_and_operator_bypass():
    with _factory()() as s:
        rbac_service.seed_rbac(s)
        s.add(Tenant(id="A", name="A"))
        s.commit()
        operator_user = rbac_service.provision_user(s, tenant_id="A", email="op@a.test")
        rbac_service.assign_role(s, user_id=operator_user.id, role_name="Operator", tenant_id="A")
        tenant_service.provision_api_key(
            s, tenant_id="A", name="op", raw_key="op-A", user_id=operator_user.id
        )
        tenant_service.provision_api_key(s, tenant_id="A", name="nu", raw_key="nu-A")

        op = rbac_service.resolve_principal(s, api_key="op-A")
        assert op.tenant_id == "A" and op.user_id == operator_user.id
        assert op.has("execute_approved_action") and op.has("view_audit")
        assert not op.has("approve_action")  # Operator cannot approve

        bypass = rbac_service.resolve_principal(s, api_key=None)
        assert bypass.is_operator and bypass.has("approve_action")

        nouser = rbac_service.resolve_principal(s, api_key="nu-A")
        assert not nouser.is_operator and nouser.permissions == frozenset()
