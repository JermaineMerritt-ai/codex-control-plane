"""Buyer-facing evidence packet demo (read-only; no Gmail; existing services).

Builds one complete governed-action chain and prints its evidence packet as an
executive summary, JSON, and Markdown. It uses only existing services
(no new product behavior, no hidden automation, no live Gmail), and writes to a
throwaway SQLite database so it never touches your working data.

Run:  python -m scripts.demo_evidence_packet
"""

from __future__ import annotations

import os
import tempfile

from sqlalchemy.orm import Session, sessionmaker

DEMO_TENANT_ID = "demo-tenant"
DEMO_TENANT_NAME = "Demo Tenant"


def seed_demo(session: Session) -> str:
    """Create a complete demo chain via existing services; return the action id."""
    from db.models import Tenant
    from services import (
        approval_service,
        control_catalog,
        evidence_graph,
        job_service,
        rbac_service,
    )
    from services.job_types import CHAT_ORCHESTRATE, EMAIL_SEND_APPROVED

    rbac_service.seed_rbac(session)
    control_catalog.seed_control_catalog(session)

    if session.get(Tenant, DEMO_TENANT_ID) is None:
        session.add(Tenant(id=DEMO_TENANT_ID, name=DEMO_TENANT_NAME))
        session.commit()

    ai = evidence_graph.create_ai_system(
        session, tenant_id=DEMO_TENANT_ID, name="Pharmacy AI Documentation Assistant",
        description="Demo AI system",
    )
    workflow = evidence_graph.create_workflow(
        session, tenant_id=DEMO_TENANT_ID, name="Outbound email workflow", ai_system_id=ai.id,
    )
    source_job = job_service.create_job(
        session, job_type=CHAT_ORCHESTRATE, tenant_id=DEMO_TENANT_ID, payload={"demo": True},
    )
    approval = approval_service.create_request(
        session, kind="job.gate", tenant_id=DEMO_TENANT_ID, job_id=source_job.id, payload={},
    )
    approval_service.approve(
        session, approval.id, actor="compliance.officer", note="approved for demo",
        tenant_id=DEMO_TENANT_ID,
    )
    exec_job = job_service.create_job(
        session, job_type=EMAIL_SEND_APPROVED, tenant_id=DEMO_TENANT_ID,
        payload={"approval_id": approval.id},
    )
    action = evidence_graph.create_governed_action(
        session, tenant_id=DEMO_TENANT_ID, action_type="email.send", workflow_id=workflow.id,
        source_job_id=source_job.id, approval_id=approval.id, execution_job_id=exec_job.id,
        policy_version="v1", policy_decision="requires_approval", status="executed",
    )

    framework = next(f for f in control_catalog.list_frameworks(session) if f.name == "NIST AI RMF")
    control = control_catalog.list_controls(session, framework.id)[0]
    regulation = control_catalog.list_regulations(session)[0]
    control_catalog.create_action_control_mapping(
        session, tenant_id=DEMO_TENANT_ID, governed_action_id=action.id,
        control_id=control.id, regulation_id=regulation.id, rationale="demo mapping",
    )
    evidence_graph.record_evidence_artifact(
        session, tenant_id=DEMO_TENANT_ID, governed_action_id=action.id,
        artifact_type="approval_record", uri="mem://demo/approval",
    )
    return action.id


def build_demo_packet(session: Session) -> dict:
    """Seed the demo chain and return its governed-action evidence packet."""
    from services import evidence_packet

    action_id = seed_demo(session)
    return evidence_packet.build_action_packet(
        session, governed_action_id=action_id, tenant_id=DEMO_TENANT_ID
    )


def _print_section(title: str, body: str) -> None:
    print("=" * 72)
    print(title)
    print("=" * 72)
    print(body)
    print()


def main() -> None:
    # The packet renders use unicode (e.g. arrows, em dashes); make stdout UTF-8
    # so the demo prints cleanly on a non-UTF-8 console (e.g. Windows).
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

    # Throwaway DB so the demo never touches working data; set before db import.
    tmp_dir = tempfile.mkdtemp(prefix="codex-demo-")
    db_path = os.path.join(tmp_dir, "demo.db").replace(os.sep, "/")
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from db.session import get_engine, init_db
    from services import evidence_packet

    engine = get_engine()
    init_db(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        packet = build_demo_packet(session)

    _print_section("EXECUTIVE SUMMARY", packet["executive_summary"])
    _print_section("EVIDENCE PACKET (JSON)", evidence_packet.render_json(packet))
    _print_section("EVIDENCE PACKET (MARKDOWN)", evidence_packet.render_markdown(packet))


if __name__ == "__main__":
    main()
