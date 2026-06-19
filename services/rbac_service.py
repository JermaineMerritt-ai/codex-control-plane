"""Role-based access control (PR 4 — identity & permissions).

Builds on PR 3 tenant isolation. A request resolves to a ``Principal`` carrying
its tenant, user, and permission set:

1. Valid API key **with** a ``user_id``  -> RBAC enforced (the user's role
   permissions).
2. Valid API key **without** a ``user_id`` -> no permissions; protected actions
   denied by default.
3. Invalid API key -> ``InvalidApiKey`` (401 at the edge).
4. **No** API key -> operator/system bypass (full access) so the local demo and
   background worker keep working. This bypass is explicit and can be disabled
   with ``REQUIRE_RBAC_FOR_OPERATOR=true`` (default off in PR 4).

RBAC is layered **on top of** tenant isolation and the approval gate — it never
replaces or bypasses either. No UI, no connectors, no evidence-graph logic here.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.governance_seed import PERMISSION_NAMES
from db.models import ApiKey, Permission, Role, RolePermission, User, UserRole
from services.tenant_service import InvalidApiKey, hash_api_key

# --- Permission catalog (the 9 governance permissions) ---------------------
P_CREATE = "create_governed_action"
P_APPROVE = "approve_action"
P_REJECT = "reject_action"
P_EXECUTE = "execute_approved_action"
P_VIEW_AUDIT = "view_audit"
P_EXPORT_EVIDENCE = "export_evidence"
P_MANAGE_POLICIES = "manage_policies"
P_MANAGE_CONTROLS = "manage_controls"
P_MANAGE_USERS = "manage_users"

# --- Role -> permission matrix (system roles, tenant-agnostic templates) ----
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "Owner": set(PERMISSION_NAMES),  # all 9
    "Admin": set(PERMISSION_NAMES) - {P_MANAGE_USERS},
    "Compliance Officer": {
        P_APPROVE,
        P_REJECT,
        P_VIEW_AUDIT,
        P_EXPORT_EVIDENCE,
        P_MANAGE_CONTROLS,
        P_MANAGE_POLICIES,
    },
    "Auditor": {P_VIEW_AUDIT, P_EXPORT_EVIDENCE},
    "Operator": {P_CREATE, P_EXECUTE, P_VIEW_AUDIT},
    # Reviewer (Phase 2): approves/rejects governed actions; read-only on audit.
    # Deliberately has no create permission — separation of duties from Operator.
    "Reviewer": {P_APPROVE, P_REJECT, P_VIEW_AUDIT},
    "Viewer": {P_VIEW_AUDIT},
}


@dataclass(frozen=True)
class Principal:
    tenant_id: str | None
    user_id: str | None
    permissions: frozenset[str]
    is_operator: bool

    def has(self, permission: str) -> bool:
        return self.is_operator or permission in self.permissions


# --- Seeding ---------------------------------------------------------------

def seed_rbac(session: Session) -> None:
    """Idempotently seed the permission catalog, system roles, and the
    role->permission mappings. Safe to call repeatedly (e.g. at startup)."""
    perms: dict[str, Permission] = {}
    for name in PERMISSION_NAMES:
        perm = session.execute(
            select(Permission).where(Permission.name == name)
        ).scalar_one_or_none()
        if perm is None:
            perm = Permission(name=name)
            session.add(perm)
            session.flush()
        perms[name] = perm

    for role_name, perm_names in ROLE_PERMISSIONS.items():
        role = session.execute(
            select(Role).where(Role.tenant_id.is_(None), Role.name == role_name)
        ).scalar_one_or_none()
        if role is None:
            role = Role(tenant_id=None, name=role_name, is_system=True)
            session.add(role)
            session.flush()
        for perm_name in perm_names:
            perm = perms[perm_name]
            link = session.execute(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id,
                )
            ).scalar_one_or_none()
            if link is None:
                session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    session.commit()


# --- Provisioning helpers (ops/tests) --------------------------------------

def provision_user(
    session: Session, *, tenant_id: str, email: str, display_name: str | None = None
) -> User:
    user = User(tenant_id=tenant_id, email=email, display_name=display_name)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def assign_role(session: Session, *, user_id: str, role_name: str, tenant_id: str | None = None) -> UserRole:
    role = session.execute(
        select(Role).where(Role.tenant_id.is_(None), Role.name == role_name)
    ).scalar_one()
    link = UserRole(tenant_id=tenant_id, user_id=user_id, role_id=role.id)
    session.add(link)
    session.commit()
    return link


# --- Resolution ------------------------------------------------------------

def _permissions_for_user(session: Session, user_id: str) -> frozenset[str]:
    stmt = (
        select(Permission.name)
        .select_from(UserRole)
        .join(RolePermission, RolePermission.role_id == UserRole.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(UserRole.user_id == user_id)
    )
    return frozenset(session.execute(stmt).scalars().all())


def resolve_principal(session: Session, *, api_key: str | None) -> Principal:
    """Resolve the caller to a Principal (see module docstring for the rules)."""
    if not api_key:
        from app.config import get_settings

        # Operator/system bypass unless explicitly hardened off.
        is_operator = not get_settings().require_rbac_for_operator
        return Principal(tenant_id=None, user_id=None, permissions=frozenset(), is_operator=is_operator)

    row = session.execute(
        select(ApiKey).where(
            ApiKey.key_hash == hash_api_key(api_key),
            ApiKey.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        raise InvalidApiKey("invalid_api_key")

    if row.user_id is None:
        # Tenant-bound key with no user => no permissions (protected actions denied).
        return Principal(
            tenant_id=row.tenant_id, user_id=None, permissions=frozenset(), is_operator=False
        )

    return Principal(
        tenant_id=row.tenant_id,
        user_id=row.user_id,
        permissions=_permissions_for_user(session, row.user_id),
        is_operator=False,
    )
