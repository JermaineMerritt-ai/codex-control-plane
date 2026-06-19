# Phase 2 Grant / SBIR Use Case — AI Governance Evidence

A reviewer-facing narrative for grant / SBIR / agency contexts. It describes what
the merged Phase 2 system actually does and the evidence it produces. CodexDominion
**supports evidence collection, control mapping, audit readiness, and governance
workflows**; it does not certify, guarantee, or determine compliance, and is not a
regulatory authorization.

## Problem
Organizations are adopting AI tools, vendors, and automation faster than
governance, compliance, and audit functions can document and prove control. When
a reviewer, examiner, or contracting officer asks *who approved an AI use, under
what policy, at what risk, and where the evidence is*, the answer is typically
slow, manual, and hard to defend.

## What CodexDominion does (merged Phase 2)
An evidence-backed governance control plane that turns an AI/automation use case
into a governed record with a reproducible evidence trail:

1. **Intake** — submit an AI Vendor / Automation Governance Review.
2. **Policy evaluation** — conservative, explicit policy categories.
3. **Risk classification** — deterministic (data sensitivity, external exposure,
   autonomy, policy category) → low / medium / high. Same inputs → same result.
4. **Approval gate** — medium/high risk (or approval-gated policy) requires a
   human Reviewer; separation of duties (submitter ≠ approver).
5. **Immutable audit trail** — every step on a linked SHA-256 hash chain;
   tampering is detectable via verification.
6. **Control & regulation mapping** — actions map to recognized framework
   structures (NIST AI RMF, NIST CSF, ISO 27001/42001, SOC 2, HIPAA, GDPR, EU AI
   Act, NIST 800-53/171, CMMC, SOX, FFIEC/model-risk, DORA).
7. **Evidence packet** — exportable JSON/Markdown: governed action, policy, risk,
   approvals, full audit trail, audit-chain verification, mapped controls/
   regulations, evidence artifacts, and **identified evidence gaps**.

## Evidence artifacts a reviewer can inspect
- A governed-action record with policy decision and risk level.
- An approval history with actor and decision.
- A tamper-evident audit timeline (verifiable on demand).
- A control/regulation mapping for the action.
- An exportable evidence packet (JSON for systems, Markdown for humans).
- An explicit gap list (missing approval/controls/artifacts/audit, broken chain).

## Alignment & responsible-AI framing
The workflow operationalizes governance functions consistent with **NIST AI RMF**
(Govern / Map / Measure / Manage): governed intake and accountability (Govern),
control/regulation mapping (Map), deterministic risk classification (Measure),
and approval + audit + evidence (Manage). Mapping is descriptive and supports
audit readiness; it is not a certification.

## Reproducibility (important for review)
- Risk classification is deterministic and rule-based — auditable and repeatable.
- The audit chain re-verifies on demand (`/audit/verify`).
- The pilot is reproducible from a seed script (`scripts/seed_pilot.py`).

## Honest status
Pilot-ready for evaluation, not a production-certified deployment. Current
non-production-grade areas (database migrations, operator-bypass hardening,
evidence-packet persistence, external audit anchoring) are documented in
[PHASE2_RUNBOOK.md](PHASE2_RUNBOOK.md) and are candidate scope for a funded phase.
