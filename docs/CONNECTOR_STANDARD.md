# Connector standard (internal)

A **connector** is not done when API calls work—it is done when the **governed workflow package** is complete. Gmail v1 is the reference implementation; new connectors must match this shape unless there is an explicit, documented exception.

## 1. Durable models

- **`Job`**: Every unit of async work is a row with `type`, `status`, `payload_json`, optional `idempotency_key`, `tenant_id`.
- **`ApprovalRequest`**: Any human gate uses `kind`, `status`, `payload_json` (execution context lives here—draft ids, external refs, workflow label).
- **`AuditEvent`**: Append-only record for operator accountability (`action`, `resource_type`, `resource_id`, `metadata_json`).
- **Domain rows** (as needed): e.g. `EmailThreadRecord` / `EmailDeliveryRecord` so operators can inspect state without parsing job blobs alone.

New connectors add **narrow** tables for their domain; avoid stuffing opaque state only into jobs.

## 2. Job types

- **Intake / orchestration** job: one entry type per user-facing flow (e.g. `chat.orchestrate`).
- **Execution** job: separate type for side-effecting work after approval (e.g. `email.send_approved`).

Job type strings live in a single module (e.g. `services/job_types.py`) and are referenced by workers and services—no scattered string literals.

## 3. Policy and approval

- Classify user intent → **policy evaluation** (`allowed` / `blocked` / `requires_approval`).
- If approval is required: create **`ApprovalRequest`**, audit **`approval.created`**, return structured result pointing at `approval_id`.
- **Approve** path: validate invariants, merge execution context, enqueue execution job when appropriate, audit **`approval.approved`** / **`approval.rejected`**.

Approval payload must carry enough for **idempotent execution** and **operator inspection** (e.g. provider draft id + `workflow` discriminator).

## 4. Execution and idempotency

- Enqueue execution jobs with a **stable `idempotency_key`** (e.g. `email.send:{approval_id}`) so double-approve does not double-send.
- Worker marks job **succeeded** / **failed**; on success, persist outcome on approval and domain rows (e.g. `gmail_message_id`, delivery `sent`).
- **Dedupe**: if execution runs again after success, detect completed state and exit without repeating the side effect (document behavior per connector).

## 5. Audit events (minimum bar)

Extend `AuditAction` (or equivalent) with **connector-scoped** names, e.g.:

- `approval.created`, `approval.approved`, `approval.rejected`
- `{job_type}.enqueued`, `{job_type}.succeeded`, `{job_type}.failed`

Every approval decision and every execution enqueue / terminal outcome should be auditable.

## 6. Operator HTTP surface

Minimum pattern (may share routers):

- **Jobs**: list, get, **narrow retry** only where safe (document rules).
- **Approvals**: list, get, approve, reject.
- **Audit**: list / filter for inspection.
- **Domain**: read-only views for durable rows (e.g. deliveries by status, by approval id, by execution job id).

Protect with **`OPERATOR_API_KEY`** / `X-Operator-Key` when configured; document what stays public (e.g. `/chat`, `/health`).

## 7. Retry and safety

- Document **exactly** what may be retried, what is blocked, and HTTP / error strings (`retry_blocked_*`, etc.).
- Block retry when side effect is already recorded (approval payload, domain row, or both).
- Block retry when approval is **rejected** (new flow required).

Implement checks in **one place** (e.g. `job_service`-style helper) and test it.

## 8. Configuration and connectors

- Central **settings** (env-backed); **fail fast** when “live” or production mode is misconfigured (no silent degradation to stub/mock).
- **Single factory** builds the provider client from settings; workers and services use it—no ad-hoc construction.

## 9. Documentation (required before “done”)

- **Operator runbook**: env, run API + worker, happy path, inspection, retry, errors, intentional blocks.
- **Live setup** (if provider has OAuth/secrets): token/scopes, env vars, troubleshooting.
- **Known limitations**: single account, scope boundaries, auth model, classifier limits.
- **Demo script or curl walkthrough**: repeatable happy path (and pointer to failure/retry demo).

## 10. Tests (credible minimum)

- Unit/integration tests for policy → approval → enqueue → worker happy path (stub provider).
- Tests for **retry blocked** cases and **operator auth** on gated routes.
- Optional **opt-in live** test module gated by env (does not run in default CI).

---

**Reference implementation:** this repo’s Gmail slice (`services/email_service.py`, `services/approval_service.py`, `workers/tasks.py`, `app/api/*`, `docs/GMAIL_OPERATOR_RUNBOOK.md`).

**Anti-pattern:** one-off scripts, magic strings, silent stub fallback when live is configured, or operator workflows that require reading raw DB dumps.
