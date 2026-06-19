"""Idempotent pilot seed (Phase 2 / PR 10).

Creates a demo tenant with one user + API key per pilot role (Admin, Operator,
Reviewer, Auditor), seeds the RBAC roles and control catalog, and (optionally) a
sample governance-review run so the console has something to show. Safe to run
repeatedly — existing users/keys/runs are reused, not duplicated.

Run (targets the SAME database your API uses — set DATABASE_URL the same):
    python -m scripts.seed_pilot
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

DEMO_TENANT_ID = "pilot-tenant"
DEMO_TENANT_NAME = "CodexDominion Pilot Tenant"

# (role, fixed demo API key, user email). Fixed keys keep the guided demo
# reproducible; rotate before any real/external use.
ROLE_KEYS: list[tuple[str, str, str]] = [
    ("Admin", "pilot-admin-key", "admin@pilot.test"),
    ("Operator", "pilot-operator-key", "operator@pilot.test"),
    ("Reviewer", "pilot-reviewer-key", "reviewer@pilot.test"),
    ("Auditor", "pilot-auditor-key", "auditor@pilot.test"),
]


def seed_pilot(session: Session) -> dict[str, Any]:
    """Idempotently seed the pilot tenant, role users, keys, and a sample run."""
    from db.models import ApiKey, Role, Tenant, User, UserRole
    from services import control_catalog, governance_workflow, rbac_service, tenant_service

    rbac_service.seed_rbac(session)
    control_catalog.seed_control_catalog(session)

    if session.get(Tenant, DEMO_TENANT_ID) is None:
        session.add(Tenant(id=DEMO_TENANT_ID, name=DEMO_TENANT_NAME))
        session.commit()

    credentials: list[dict[str, str]] = []
    for role_name, raw_key, email in ROLE_KEYS:
        user = session.execute(
            select(User).where(User.tenant_id == DEMO_TENANT_ID, User.email == email)
        ).scalar_one_or_none()
        if user is None:
            user = rbac_service.provision_user(session, tenant_id=DEMO_TENANT_ID, email=email)

        role_row = session.execute(
            select(Role).where(Role.tenant_id.is_(None), Role.name == role_name)
        ).scalar_one()
        has_role = session.execute(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role_row.id)
        ).scalar_one_or_none()
        if has_role is None:
            rbac_service.assign_role(
                session, user_id=user.id, role_name=role_name, tenant_id=DEMO_TENANT_ID
            )

        existing_key = session.execute(
            select(ApiKey).where(ApiKey.key_hash == tenant_service.hash_api_key(raw_key))
        ).scalar_one_or_none()
        if existing_key is None:
            tenant_service.provision_api_key(
                session, tenant_id=DEMO_TENANT_ID, name=role_name, raw_key=raw_key, user_id=user.id
            )
        credentials.append({"role": role_name, "email": email, "api_key": raw_key})

    # Optional sample run — only if the tenant has no governance-review run yet.
    runs = governance_workflow.list_runs(session, tenant_id=DEMO_TENANT_ID)
    if runs:
        sample_run_id = runs[0]["governed_action_id"]
    else:
        run = governance_workflow.submit_vendor_governance_review(
            session,
            tenant_id=DEMO_TENANT_ID,
            actor="seed",
            vendor_name="Acme Pharmacy AI",
            system_type="documentation assistant",
            intended_use="clinical note drafting",
            data_sensitivity="phi",
            external_exposure=True,
            autonomy_level="assisted",
        )
        sample_run_id = run["governed_action_id"]

    return {"tenant_id": DEMO_TENANT_ID, "credentials": credentials, "sample_run_id": sample_run_id}


def main() -> None:
    from db.session import get_engine, init_db

    engine = get_engine()
    init_db(engine)
    factory = sessionmaker(bind=engine, future=True)
    with factory() as session:
        summary = seed_pilot(session)

    print("=" * 64)
    print("CodexDominion pilot seed complete")
    print("=" * 64)
    print(f"Tenant: {summary['tenant_id']}")
    print(f"Sample run (governed_action_id): {summary['sample_run_id']}")
    print("\nAPI keys (header: X-Api-Key) - for the console at /console:")
    for c in summary["credentials"]:
        print(f"  {c['role']:<9} {c['api_key']:<20} ({c['email']})")
    print("\nReminder: run the API WITHOUT OPERATOR_API_KEY so the console's")
    print("X-Api-Key RBAC is the auth path. Rotate these demo keys before real use.")


if __name__ == "__main__":
    main()
