# Evidence Graph

**Scope:** PR 6 of the Enterprise Governance Foundation — **data/service
foundation only**. It adds tenant-scoped create/read helpers for the governance
graph and a read-only assembler that connects the chain. There is **no export
packet generation** (PR 7), no UI, no connectors, and no change to the Gmail
governed execution flow.

This **supports evidence collection, control mapping, audit readiness, and
governance workflows.** It makes no compliance claim.

## The chain

```
AI System → Workflow → Governed Action → Policy Decision → Approval
  → Execution → Audit Event → Control Mapping → Regulation → Evidence Artifact
```

`GovernedAction` is the hub. It carries the links that connect existing
execution concepts to the graph **without changing the pipeline**:

| Field | Connects to |
|---|---|
| `workflow_id` | `Workflow` → `ai_system_id` → `AiSystem` |
| `policy_version`, `policy_decision` | the policy decision |
| `approval_id` | `ApprovalRequest` |
| `source_job_id`, `execution_job_id` | `Job` (intake + execution) |
| (by resource id) | `AuditEvent`s for the approval / jobs |
| `governed_action_id` | `GovernedActionControlMapping` → `Control` → `ControlFramework`, `Regulation` |
| `governed_action_id` | `EvidenceArtifact` |

## Services (`services/evidence_graph.py`)

- **Create (tenant-scoped):** `create_ai_system`, `create_data_source`,
  `create_workflow`, `create_governed_action`, `create_risk_assessment`,
  `record_evidence_artifact`.
- **Read (tenant-scoped):** `list_ai_systems` / `get_ai_system`,
  `list_workflows`, `list_governed_actions` / `get_governed_action`,
  `list_evidence_artifacts`.
- **Assemble (read-only):** `get_evidence_graph(governed_action_id, tenant_id)`
  walks the chain and returns the connected records, or `None` for a missing /
  cross-tenant action. It does **not** persist or export anything.

All reads are tenant-scoped (consistent with PR 3): passing a `tenant_id`
restricts results to that tenant; cross-tenant lookups return `None` / empty.

## Linking execution to the graph

The pipeline (intake → policy → approval → execution → delivery → audit) is
unchanged. A `GovernedAction` is created separately and references the existing
approval / jobs via its link fields, so the graph can be assembled over real
execution records without touching the governed flow.

## Endpoints

Tenant-scoped and gated by `view_audit` (these expose governance/evidence data):

| Route | Returns |
|---|---|
| `GET /evidence/ai-systems` | the tenant's AI systems |
| `GET /evidence/actions` | the tenant's governed actions |
| `GET /evidence/actions/{id}/graph` | the assembled chain for one action (404 if missing/cross-tenant) |

The operator/system path (no API key) reads unscoped (demo/worker), as elsewhere.

## What this PR does NOT do

- No `EvidencePacket` rows, no JSON/Markdown export, no buyer-facing report (PR 7).
- No automatic creation of graph nodes from the pipeline (no broad automation).
- No compliance scoring or attestation.

## Tests

`tests/test_evidence_graph.py`: full-chain assembly (AI system → … → evidence
artifact, including audit + control + regulation linkage), tenant isolation
(Tenant B cannot read A's graph, actions, AI systems, or artifacts), and the
read endpoints (tenant-scoped, `view_audit`-gated: 200 for the owning auditor,
404 cross-tenant, 403 without permission, operator bypass works).
