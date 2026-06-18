# Evidence Packet Export

**Scope:** PR 7 of the Enterprise Governance Foundation — **export only**. It
generates exportable evidence packets from the evidence graph. Packets are
generated **on demand** (read-only); nothing is persisted, no UI is added, no
connectors are added, and the Gmail governed execution flow is unchanged.

An evidence packet **supports evidence collection, control mapping, audit
readiness, and governance workflows.** It does **not** certify, guarantee, or
represent a regulatory determination of compliance.

This is the first buyer-consumable artifact: a procurement officer, compliance
lead, auditor, or pilot customer can read or download it directly.

## Packet types (`services/evidence_packet.py`)

| Builder | Scope |
|---|---|
| `build_action_packet` | one governed action |
| `build_workflow_packet` | all governed actions in a workflow |
| `build_tenant_packet` | a tenant, optionally filtered by a created-at time range |

Each returns `None` for a missing / cross-tenant scope (tenant isolation, PR 3).

## Packet contents

- **executive_summary** (generated)
- **tenant**
- **workflow** (when applicable)
- **governed_actions**
- **approvals**
- **policy_decisions**
- **execution_history** (source + execution jobs)
- **audit_events**
- **audit_chain_verification** — reuses PR 2 verification: tenant-scoped
  self-hash (`tenant_self_hash`) for a tenant packet, or the global chain
  (`global_chain`) for the operator/system path
- **mapped_controls** and **mapped_regulations**
- **evidence_artifacts**
- **evidence_gaps** (see below)
- **generated_at** timestamp
- **disclaimer**

## Evidence gaps

The packet flags, honestly:

| Gap | Condition |
|---|---|
| `missing_approval` | a governed action has no linked approval |
| `missing_control_mappings` | no controls mapped to the action |
| `missing_evidence_artifacts` | no evidence artifacts for the action |
| `missing_audit_records` | no audit events linked to the action |
| `broken_audit_chain` | audit chain verification returned `failed` |

## Export formats

- **JSON** — `render_json` (and `GET .../export/{id}?format=json`)
- **Markdown** — `render_markdown` (and `?format=md`)

## Endpoints

All are **tenant-scoped** and require **`view_audit`**; a cross-tenant scope
returns **404** (another tenant's packet is never exposed) and a principal
without the permission gets **403** (RBAC is never bypassed).

| Route | Returns |
|---|---|
| `GET /evidence/packets/action/{id}` | governed-action packet (JSON object) |
| `GET /evidence/packets/workflow/{id}` | workflow packet (JSON object) |
| `GET /evidence/packets/export/{id}?format=json\|md` | governed-action packet rendered as JSON or Markdown |

The operator/system path (no API key) reads unscoped, consistent with the rest
of the system.

## Reuses (no duplication)

Audit chain verification (PR 2), evidence graph assembly (PR 6), control mapping
catalog (PR 5), tenant isolation (PR 3), and RBAC (PR 4).

## What this PR does NOT do

- No persistence of `EvidencePacket` rows (generation is on demand).
- No UI, no connectors, no automated compliance certification.
- No pipeline / Gmail changes.

## Tests

`tests/test_evidence_packet.py`: complete-chain packet has no gaps and a
`verified` chain; gap detection (missing approval/controls/artifacts/audit);
broken-chain gap on tamper; workflow + tenant packets; JSON + Markdown export;
service-level tenant isolation; endpoint RBAC + tenant scope (200 owner / 404
cross-tenant / 403 no-permission / operator bypass); and a procurement-safe
language check.
