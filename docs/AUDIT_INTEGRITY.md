# Audit Integrity — Tamper-Evident Hash Chain

**Scope:** PR 2 of the Enterprise Governance Foundation. This document describes
the audit hash chain only. Tenant isolation enforcement, RBAC, control mapping,
the evidence graph, and evidence-packet export are separate, later PRs and are
**not** implemented here.

This capability **supports audit readiness and creates a tamper-evident evidence
trail.** It is not a compliance certification.

## What it does

Every audit event is appended to a single, ordered, hash-linked chain. Each
event's hash commits both to its own immutable contents and to the previous
event's hash. As a result, any change to a historical event — editing a field,
deleting an event, reordering, or inserting one — is detectable, because it
invalidates that event's hash and/or the link from the next event onward.

The chain does not prevent a change to the database; it makes any such change
**provable after the fact** during verification.

## Data model

The chain reuses the existing `audit_events` table (schema added in PR 1) plus
one ordering column added in PR 2:

| Field | Role |
|---|---|
| `seq` | Monotonic position in the global chain (PR 2). |
| `previous_hash` | The `event_hash` of the preceding event (`GENESIS` for the first). |
| `event_hash` | `SHA-256` over the event's canonical core fields + `previous_hash`. |
| `action`, `resource_type`, `resource_id`, `tenant_id`, `actor`, `actor_user_id`, `actor_type`, `action_type`, `policy_version`, `decision`, `reason`, `metadata_json`, `created_at` | Immutable core fields bound into the hash. |

The genesis root is 64 zeros (`GENESIS_HASH`).

## How an event is hashed

`event_hash = SHA-256( canonical_json(core_fields, previous_hash) )`

- `canonical_json` is deterministic: keys sorted, compact separators.
- `created_at` is normalized to a UTC ISO-8601 string before hashing, so the
  hash computed at write time matches the hash recomputed at verification time
  regardless of backend (SQLite drops timezone info; PostgreSQL preserves it).
- The value used in the hash is the value stored (the timestamp is set
  explicitly at write time, not left to a database default).

## Write path

`services/audit_service.record(...)` is the **single write path** for audit
events and is unchanged for existing callers (policy, approval, execution,
delivery stages). On each call it:

1. reads the current chain head (highest `seq`),
2. sets `previous_hash` to the head's `event_hash` (or `GENESIS`),
3. assigns the next `seq`,
4. computes and stores `event_hash`,
5. commits.

Chaining is therefore automatic; no caller changes were required, and the Gmail
governed execution flow is unaffected.

## Verification

`services/audit_service.verify_chain(session)` recomputes the whole chain in
`seq` order and returns a `ChainVerificationResult`:

| `status` | Meaning |
|---|---|
| `verified` | Every event re-links and re-hashes correctly. |
| `failed` | A break was found; `broken_at_seq` and `reason` identify the first one. |
| `empty` | No chained events yet (treated as OK). |

`reason` is one of:

- `hash_mismatch` — an event's stored hash does not match a recomputation of its
  own contents (the event itself was altered).
- `broken_link` — an event's `previous_hash` does not match the prior event's
  `event_hash` (an event was deleted, reordered, or inserted).

Verification stops at and reports the **first** break.

### API

`GET /audit/verify` → `AuditChainVerificationResponse`
(`status`, `ok`, `verified_count`, `total_count`, `broken_at_seq`, `reason`).

It is exposed behind the existing operator authentication, like the other
`/audit` routes. (Role-based access for this endpoint is deferred to the RBAC
PR.)

## Threat model and limits

- **Detects:** silent edits, deletions, reordering, and insertions of historical
  events, including a forged event whose own hash was recomputed — the next
  event's link still fails.
- **Does not by itself prevent or detect:** truncation of the chain tail
  followed by re-appending a fresh consistent chain by someone who controls the
  write path. Mitigations (e.g. periodic external anchoring / signing of the
  current head) are out of scope for PR 2 and noted on the roadmap.
- The chain is **global** (one chain across all tenants). Per-tenant chain
  partitioning, if needed for tenant-scoped verification, is deferred to the
  tenant-isolation PR.

## Backward compatibility / migration

- Fresh databases get `seq` automatically via `create_all`.
- Existing SQLite databases can add the nullable column with the optional helper
  `db/migration_scripts/m002_audit_chain.py` (additive; does not run at
  startup).
- Pre-chain (legacy) rows with no `event_hash` are skipped by verification; the
  chain is considered to begin at the first chained event.

## Tests

`tests/test_audit_chain.py` proves:

- a clean chain links (`previous_hash` → prior `event_hash`) and verifies;
- an empty chain verifies;
- editing an old event's `reason` or `metadata` → `hash_mismatch` at that `seq`;
- deleting an event → `broken_link` at the following `seq`;
- a forged event with a recomputed self-hash → `broken_link` at the next `seq`;
- the pre-PR2 minimal `record()` call shape still works and chains.
