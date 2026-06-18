# RBAC — Identity & Permissions

**Scope:** PR 4 of the Enterprise Governance Foundation. Adds role-based access
control on top of PR 3 tenant isolation. No UI, no connectors, no evidence-graph
logic. Separation-of-duties (requester ≠ approver) is intentionally deferred to a
later PR.

RBAC is layered **on top of** tenant isolation and the approval gate — it never
replaces or bypasses either.

## Principal resolution

Every request resolves to a `Principal` (`tenant_id`, `user_id`, `permissions`,
`is_operator`). Resolution is keyed off the `X-Api-Key` header:

| Caller | Result | Protected actions |
|---|---|---|
| Valid API key **with** `user_id` | tenant + the user's role permissions | allowed iff permission held |
| Valid API key **without** `user_id` | tenant, **no permissions** | **denied (403)** |
| **Invalid** API key | — | **401** |
| **No** API key | operator/system bypass | allowed (full access) |

### Operator/system bypass — explicit and temporary

The no-API-key path is a **full-access bypass** so the local demo and the
background worker keep working. This is deliberate and documented, not an
accident. It can be turned off for hardening:

```
REQUIRE_RBAC_FOR_OPERATOR=true   # default: false in PR 4
```

When set, the no-key path carries **no** permissions and protected actions are
denied — i.e. real principals (API keys bound to users) become mandatory.

## Roles and permissions

Nine permissions: `create_governed_action`, `approve_action`, `reject_action`,
`execute_approved_action`, `view_audit`, `export_evidence`, `manage_policies`,
`manage_controls`, `manage_users`.

Six system roles (tenant-agnostic templates, seeded idempotently at startup):

| Role | Permissions |
|---|---|
| Owner | all 9 |
| Admin | all except `manage_users` |
| Compliance Officer | `approve_action`, `reject_action`, `view_audit`, `export_evidence`, `manage_controls`, `manage_policies` |
| Auditor | `view_audit`, `export_evidence` |
| Operator | `create_governed_action`, `execute_approved_action`, `view_audit` (note: **cannot approve** its own work) |
| Viewer | `view_audit` |

A user is bound to a tenant; an API key is bound to a tenant and (optionally) a
user; a user has roles (`UserRole`); roles grant permissions (`RolePermission`).

## Enforced routes (protected actions)

| Route | Required permission |
|---|---|
| `POST /approvals/{id}/approve` | `approve_action` |
| `POST /approvals/{id}/reject` | `reject_action` |
| `POST /jobs/{id}/retry` | `execute_approved_action` |
| `GET /audit` | `view_audit` |
| `GET /audit/verify` | `view_audit` |

The permission check runs **before** the service call. The route then scopes the
service by `principal.tenant_id`, so a permission never grants cross-tenant
access (an Admin in tenant A still cannot approve tenant B's approval — it
returns `approval_not_found`).

`/chat` (public intake) and the inspection reads (`/jobs`, `/approvals`,
`/email/*`) are not permission-gated in PR 4 — they remain tenant-scoped (PR 3).
`evidence/control admin` routes do not exist yet and will be gated when added.

## Invariants preserved

- **Tenant isolation** (PR 3) is unchanged; RBAC is an additional check.
- **The approval gate** is unchanged; RBAC never bypasses it.
- **The Gmail governed flow** is unaffected — it runs via the operator/system
  bypass (no key) in the demo and the worker.

## Tests

`tests/test_rbac.py` proves: a role-holding user can perform a protected action;
a user without the permission gets 403; tenant isolation still blocks
cross-tenant access even with the permission; a user-less API key is denied;
an invalid key gets 401; the no-key operator path still works; audit read is
gated by `view_audit`; retry is gated by `execute_approved_action` before any
lookup; and principal resolution returns the correct permission set per role.
