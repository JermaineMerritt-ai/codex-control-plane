# Tenant Isolation

**Scope:** PR 3 of the Enterprise Governance Foundation. This adds **tenant
isolation enforcement** only. Roles and permissions (RBAC) are PR 4; this PR
deliberately adds no role checks.

This capability supports multi-tenant data separation. It is not a compliance
certification.

## Model

Tenant context is derived from the caller's **credential**, never from a
client-supplied field — so a caller cannot choose to read another tenant's data.

| Caller | Resolves to | Effect |
|---|---|---|
| Valid `X-Api-Key` (an `api_keys` row) | that key's `tenant_id` | **scoped** — sees only its tenant |
| No API key (operator/dev key, system worker) | `None` | **unscoped** — full access (preserves the demo + worker) |
| Presented-but-invalid API key | — | **401** (never falls back to full access) |

Resolution lives in `services/tenant_service.py` (`resolve_tenant_id`,
`hash_api_key`, `provision_api_key`) and is wired into routes via the
`get_current_tenant_id` dependency in `app/deps.py`. Only the SHA-256 hash of an
API key is stored.

## Enforcement point

Isolation is enforced at the **service / data-access layer**. Every governed
read takes an optional `tenant_id`:

- `tenant_id` set → the query filters by it; a cross-tenant fetch returns
  `None` / empty (a 404 at the API, never a leak of another tenant's record).
- `tenant_id=None` → unscoped, for the operator/dev path and the system worker
  (backward compatible).

Routes always pass the resolved tenant, so the running API is scoped; internal
system paths pass `None` intentionally.

### Scoped reads (and writes)

| Area | Scoped functions |
|---|---|
| Jobs | `get_job_by_id`, `list_jobs`, `retry_failed_job` |
| Approvals | `get_request`, `list_approvals`, **`approve`, `reject`** (cannot act cross-tenant) |
| Audit | `list_audit_events`, `list_for_resource`, `verify_tenant_events` |
| Email | `list_deliveries`, `get_delivery_by_approval_id`, `get_delivery_by_execution_job_id`, `get_thread_summary` |
| Writes | `/chat` stamps the job with the credential's tenant (clients cannot spoof via body) |

**Intentionally global:** `claim_next_pending` — the background worker is a
system actor that processes all tenants' jobs; isolation applies to API callers,
not the worker. The worker preserves each job's `tenant_id` through execution,
and audit events remain tenant-stamped.

## Audit verification under tenancy

The audit hash chain remains **global** (one chain across all tenants), so
full-chain link verification (`verify_chain`) is unchanged and still passes after
tenant-scoped reads.

For tenant callers, `GET /audit/verify` runs `verify_tenant_events(tenant_id)`,
which recomputes the **self-hash of each of that tenant's events**. This proves
none of that tenant's records were individually altered. It is intentionally
**not** a full-chain link proof — because the chain is global, cross-event link
verification stays the job of the global check (the operator/system path). A
tenant caller cannot see the global event count or another tenant's events.

Per-tenant chain partitioning (which would make per-tenant link verification
possible) is a deliberate future option, not done here.

## Limits / deferred

- **`tenant_id` stays nullable.** Enforcement is at the service layer; making the
  column non-null (with backfill) is a later hardening, kept out to avoid a
  migration in this PR. No schema change ships in PR 3.
- **The operator key is still full-access** (unscoped). Tightening it to a real
  principal with roles is PR 4 (RBAC).
- **Per-tenant audit-chain verification** is approximate (self-hash only) by
  design while the chain is global.

## Tests

`tests/test_tenant_isolation.py` proves Tenant A cannot read Tenant B's jobs,
approvals, audit records, or deliveries; cannot act on B's approvals; cannot
verify or export B's scoped audit view; that the operator/unscoped path still
sees everything; that the global chain still verifies after tenant-scoped
operations; and that an API key resolves to its bound tenant while an unknown key
is rejected.
