"""Tenant isolation enforcement tests (PR 3).

Proves that a tenant-scoped caller cannot read or act on another tenant's
governed objects, that the operator/dev (unscoped) path still sees everything,
and that the global audit hash chain still verifies after tenant-scoped reads.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.main import app
from db.models import EmailDeliveryRecord, Tenant
from db.session import get_engine
from services import (
    approval_service,
    audit_service,
    email_persistence,
    job_service,
    tenant_service,
)
from services.job_types import CHAT_ORCHESTRATE

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"


def _factory():
    return sessionmaker(bind=get_engine(), future=True)


def _make_tenant(session, tenant_id: str) -> None:
    session.add(Tenant(id=tenant_id, name=tenant_id.upper()))
    session.commit()


def _seed_tenant(session, tenant_id: str):
    """Create a job + approval + delivery + audit trail for one tenant."""
    job = job_service.create_job(
        session, job_type=CHAT_ORCHESTRATE, tenant_id=tenant_id, payload={"x": 1}
    )
    appr = approval_service.create_request(  # also writes a tenant-stamped audit event
        session,
        kind="job.gate",
        tenant_id=tenant_id,
        job_id=job.id,
        payload={"gmail_draft_id": f"draft-{tenant_id}", "workflow": "email.outbound"},
    )
    delivery = EmailDeliveryRecord(
        tenant_id=tenant_id,
        thread_external_id=f"thread-{tenant_id}",
        approval_id=appr.id,
        execution_job_id=job.id,
        status="sent",
        gmail_message_id=f"msg-{tenant_id}",
    )
    session.add(delivery)
    session.commit()
    return job, appr, delivery


def _seed_both(session):
    _make_tenant(session, TENANT_A)
    _make_tenant(session, TENANT_B)
    a = _seed_tenant(session, TENANT_A)
    b = _seed_tenant(session, TENANT_B)
    return a, b


def test_tenant_a_cannot_read_tenant_b_jobs():
    with _factory()() as s:
        (job_a, _, _), (job_b, _, _) = _seed_both(s)
        assert job_service.get_job_by_id(s, job_b.id, tenant_id=TENANT_A) is None
        assert job_service.get_job_by_id(s, job_a.id, tenant_id=TENANT_A) is not None
        listed = job_service.list_jobs(s, tenant_id=TENANT_A)
        ids = {j.id for j in listed}
        assert job_a.id in ids and job_b.id not in ids
        assert all(j.tenant_id == TENANT_A for j in listed)


def test_tenant_a_cannot_read_tenant_b_approvals():
    with _factory()() as s:
        (_, appr_a, _), (_, appr_b, _) = _seed_both(s)
        assert approval_service.get_request(s, appr_b.id, tenant_id=TENANT_A) is None
        assert approval_service.get_request(s, appr_a.id, tenant_id=TENANT_A) is not None
        listed = approval_service.list_approvals(s, tenant_id=TENANT_A)
        ids = {r.id for r in listed}
        assert appr_a.id in ids and appr_b.id not in ids


def test_tenant_a_cannot_act_on_tenant_b_approval():
    with _factory()() as s:
        _, (_, appr_b, _) = _seed_both(s)
        with pytest.raises(ValueError, match="approval_not_found"):
            approval_service.approve(s, appr_b.id, actor="op", note="x", tenant_id=TENANT_A)
        with pytest.raises(ValueError, match="approval_not_found"):
            approval_service.reject(s, appr_b.id, actor="op", reason="x", tenant_id=TENANT_A)


def test_tenant_a_cannot_read_tenant_b_audit_records():
    with _factory()() as s:
        (_, appr_a, _), (_, appr_b, _) = _seed_both(s)
        events_a = audit_service.list_audit_events(s, tenant_id=TENANT_A)
        assert events_a and all(e.tenant_id == TENANT_A for e in events_a)
        # B's approval audit trail is invisible when scoped to A.
        assert audit_service.list_for_resource(
            s, resource_type="approval", resource_id=appr_b.id, tenant_id=TENANT_A
        ) == []
        assert audit_service.list_for_resource(
            s, resource_type="approval", resource_id=appr_a.id, tenant_id=TENANT_A
        ) != []


def test_tenant_a_cannot_access_tenant_b_deliveries():
    with _factory()() as s:
        (job_a, appr_a, _), (job_b, appr_b, _) = _seed_both(s)
        assert email_persistence.get_delivery_by_approval_id(s, appr_b.id, tenant_id=TENANT_A) is None
        assert email_persistence.get_delivery_by_approval_id(s, appr_a.id, tenant_id=TENANT_A) is not None
        assert email_persistence.get_delivery_by_execution_job_id(s, job_b.id, tenant_id=TENANT_A) is None
        listed = email_persistence.list_deliveries(s, tenant_id=TENANT_A)
        assert listed and all(d.tenant_id == TENANT_A for d in listed)


def test_tenant_a_cannot_verify_or_export_tenant_b_scoped_view():
    with _factory()() as s:
        _seed_both(s)
        # Scoped verify only ever covers the caller's own tenant.
        res_a = audit_service.verify_tenant_events(s, TENANT_A)
        assert res_a.status == "verified"
        assert res_a.total_count == len(audit_service.list_audit_events(s, tenant_id=TENANT_A))
        # The two tenants' scoped exports are disjoint — A's view never contains B.
        export_a = {e.id for e in audit_service.list_audit_events(s, tenant_id=TENANT_A)}
        export_b = {e.id for e in audit_service.list_audit_events(s, tenant_id=TENANT_B)}
        assert export_a and export_b
        assert export_a.isdisjoint(export_b)


def test_operator_unscoped_path_still_sees_everything():
    """The demo/operator path (tenant_id=None) is unscoped — back-compatible."""
    with _factory()() as s:
        (job_a, _, _), (job_b, _, _) = _seed_both(s)
        all_jobs = {j.id for j in job_service.list_jobs(s)}  # tenant_id=None
        assert {job_a.id, job_b.id} <= all_jobs
        assert job_service.get_job_by_id(s, job_b.id) is not None


def test_global_audit_chain_still_verifies_after_tenant_scoped_ops():
    with _factory()() as s:
        _seed_both(s)
        # Exercise tenant-scoped reads, then confirm the global chain is intact.
        audit_service.list_audit_events(s, tenant_id=TENANT_A)
        audit_service.verify_tenant_events(s, TENANT_B)
        assert audit_service.verify_chain(s).status == "verified"


def test_chat_does_not_trust_body_tenant_id():
    """Public /chat must not let an unauthenticated caller stamp a job with an
    arbitrary tenant via the request body."""
    with TestClient(app) as client:
        resp = client.post(
            "/chat",
            json={"tenant_id": TENANT_B, "session_id": "s1", "message": "hi"},
        )
        assert resp.status_code == 200
        job_id = resp.json()["job_id"]
    with _factory()() as s:
        job = job_service.get_job_by_id(s, job_id)  # unscoped read
        assert job is not None
        assert job.tenant_id is None  # body "tenant-b" ignored, not spoofable


def test_chat_binds_job_to_api_key_tenant_not_body():
    with _factory()() as s:
        _make_tenant(s, TENANT_A)
        tenant_service.provision_api_key(s, tenant_id=TENANT_A, name="k", raw_key="key-A")
    with TestClient(app) as client:
        resp = client.post(
            "/chat",
            json={"tenant_id": TENANT_B, "session_id": "s2", "message": "hi"},
            headers={"X-Api-Key": "key-A"},
        )
        job_id = resp.json()["job_id"]
    with _factory()() as s:
        job = job_service.get_job_by_id(s, job_id)
        assert job is not None
        assert job.tenant_id == TENANT_A  # credential wins; body tenant ignored


def test_api_key_resolves_to_bound_tenant_and_rejects_unknown():
    with _factory()() as s:
        _make_tenant(s, TENANT_A)
        tenant_service.provision_api_key(s, tenant_id=TENANT_A, name="primary", raw_key="secret-A")
        assert tenant_service.resolve_tenant_id(s, api_key="secret-A") == TENANT_A
        # No key => unscoped operator/dev path.
        assert tenant_service.resolve_tenant_id(s, api_key=None) is None
        # A presented-but-invalid key must never fall back to full access.
        with pytest.raises(tenant_service.InvalidApiKey):
            tenant_service.resolve_tenant_id(s, api_key="not-a-real-key")
