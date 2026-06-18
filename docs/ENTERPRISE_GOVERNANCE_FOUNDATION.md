# Enterprise Governance Foundation

**Status:** Phase 1 complete (PRs 1–8). This document is the packaging overview;
each capability has its own deep-dive doc, linked below.

These capabilities **support evidence collection, control mapping, audit
readiness, and governance workflows.** They do not certify, guarantee, or
determine compliance, and are not a regulatory authorization. This is a pattern
and reference implementation, not a finished SaaS or a production-certified
system.

## What Phase 1 adds (on top of the governed execution pattern)

| Capability | Doc |
|---|---|
| Tamper-evident audit hash chain + verification | [AUDIT_INTEGRITY.md](AUDIT_INTEGRITY.md) |
| Multi-tenant isolation (credential-bound) | [TENANT_ISOLATION.md](TENANT_ISOLATION.md) |
| Identity + RBAC (roles/permissions) | [RBAC.md](RBAC.md) |
| Regulation + control mapping catalog | [CONTROL_MAPPING.md](CONTROL_MAPPING.md) |
| Evidence graph foundation | [EVIDENCE_GRAPH.md](EVIDENCE_GRAPH.md) |
| Evidence packet export (JSON + Markdown) | [EVIDENCE_PACKET_EXPORT.md](EVIDENCE_PACKET_EXPORT.md) |

The original governed execution pattern (intake → policy → approval → execution →
delivery → audit) is unchanged; Phase 1 layered governance **around** it without
altering the Gmail flow.

## Architecture summary

- **FastAPI + SQLAlchemy 2.0**, SQLite by default (`DATABASE_URL` overridable).
- **Governed pipeline (unchanged):** durable jobs → policy → approval gate →
  worker execution → delivery + audit.
- **Audit:** every audit event is appended to a global SHA-256 hash chain;
  `verify_chain` (global) and `verify_tenant_events` (tenant self-hash) detect
  tampering.
- **Tenancy:** a request resolves to a tenant from its API key; reads/writes are
  scoped at the service layer. No key = operator/system path.
- **RBAC:** an API key may bind a user whose roles grant permissions; protected
  actions (approve/reject/retry/audit read/audit verify) require the matching
  permission. RBAC is layered on top of tenant isolation and the approval gate.
- **Governance graph:** AI System → Workflow → Governed Action → Policy Decision
  → Approval → Execution → Audit Event → Control Mapping → Regulation →
  Evidence Artifact, assembled read-only from existing records.
- **Evidence packet:** an on-demand, exportable summary (JSON/Markdown) of the
  graph for an action, workflow, or tenant, including audit-chain verification
  and identified evidence gaps.

## Security model summary

- **Tenant isolation:** tenant comes from the credential, never a client field;
  cross-tenant reads return empty/404 (never a leak). See TENANT_ISOLATION.md.
- **RBAC:** valid key + user → enforced permissions; valid key without a user →
  protected actions denied; invalid key → 401; **no key → operator/system
  bypass** (explicit, documented, toggleable via `REQUIRE_RBAC_FOR_OPERATOR`,
  default off). See RBAC.md.
- **Audit integrity:** tamper-evident chain; tenant callers verify their own
  events only and cannot see global counts. See AUDIT_INTEGRITY.md.
- **Approval gate:** unchanged; RBAC and tenancy are additional checks, never a
  bypass.

## Remaining limitations

- The audit chain is **global**; per-tenant verification is self-hash only.
- Tail-truncation of the chain is not self-detecting (external anchoring is a
  Phase 2 item).
- `tenant_id` remains nullable (enforced at the service layer, not the column).
- The operator/no-key path is full-access by default.
- Catalog controls are representative top-level structures, not complete
  control catalogues.
- Evidence packets are generated on demand and not persisted.

## What is not yet production-grade

- **Migrations:** no Alembic; schema is created via `create_all` plus optional
  additive SQLite helpers. Production needs a real migration tool.
- **Database:** SQLite by default; PostgreSQL is supported by the code but not
  exercised in CI.
- **Operator bypass** must be hardened (`REQUIRE_RBAC_FOR_OPERATOR=true` +
  provisioned principals) before multi-tenant production use.
- **No UI**, no connector expansion beyond the Gmail reference, single-process
  polling worker.

## Phase 2 roadmap (not built)

1. Real migrations (Alembic) and a CI-exercised PostgreSQL path.
2. Harden the operator bypass; mandatory principals in production.
3. Per-tenant audit-chain partitioning and/or external head anchoring/signing.
4. Evidence packet persistence + signing; buyer-retrievable stored packets.
5. Separation-of-duties (requester ≠ approver).
6. Pipeline-driven creation of governed actions and evidence artifacts.
7. Additional connectors and an operator/reviewer UI.

See also [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) and [STRUCTURE.md](STRUCTURE.md).
