# Phase 2 Demo Script — Buyer Walkthroughs

A 5-minute guided demo of the live pilot loop, tailored per buyer. Setup once
(see [PHASE2_RUNBOOK.md](PHASE2_RUNBOOK.md)): seed, run the API without
`OPERATOR_API_KEY`, open `http://127.0.0.1:8099/console`.

CodexDominion **supports audit readiness, evidence collection, and governance
workflows.** It does not certify, guarantee, or determine compliance, and is not
a regulatory authorization. Demo keys are non-production.

## The core loop (same for every buyer)
1. **Operator** (`pilot-operator-key`) submits an *AI Vendor / Automation
   Governance Review* → policy + **deterministic risk** auto-evaluate →
   medium/high risk **requires approval**.
2. **Reviewer** (`pilot-reviewer-key`) approves/rejects — separation of duties:
   the Operator cannot approve their own submission.
3. **Auditor** (`pilot-auditor-key`) exports the **evidence packet** (JSON/MD):
   governed action, policy, risk, approval, **step-by-step audit trail**,
   audit-chain verification, mapped controls/regulations, evidence gaps.

The one-liner: *"Who approved this AI use, under what policy, at what risk — and
can you prove it, with the gaps stated honestly?"*

## 1 · Government contractor — audit & procurement readiness
- **Frame:** "When an auditor or contracting officer asks who approved an AI/
  automation use and to show the evidence, how fast — and is it tamper-evident?"
- **Show:** submit a high-risk vendor (regulated data, autonomous) → approval
  required → Reviewer approves → export packet → point at the **tamper-evident
  audit chain verification = verified** and the **complete step trail**.
- **Close:** "That packet is the artifact you hand to audit/procurement review."

## 2 · Healthcare compliance — AI/vendor oversight
- **Frame:** "AI and vendors are entering pharmacy/clinical workflows faster than
  governance can keep up. Can you prove control over PHI-touching AI?"
- **Show:** submit with `data_sensitivity = phi`, external exposure on → risk
  high → approval gate → export packet → open **Regulation & Control Mapping**
  (HIPAA: PHI protection, access control, audit logging).
- **Close:** "Evidence trail per AI/vendor use case; gaps surfaced, not hidden."

## 3 · Finance / model-risk governance
- **Frame:** "Examiners and executives want to see how a model/AI use was
  governed, who reviewed it, and where the evidence lives."
- **Show:** submit a model-risk use case → deterministic **risk classification**
  → approval gate → audit trail → control mapping (NIST, SOC 2) → export packet.
- **Close:** "Layered on your existing review — not a replacement; an evidence-
  backed governance workflow."

## 4 · Grant / SBIR reviewer
- **Frame:** "Responsible-AI and governance evidence, reproducible on demand."
- **Show:** run the loop, export the packet, then **re-run `verify`** to show the
  audit chain re-verifies; point at deterministic risk (same inputs → same
  result). Pair with [PHASE2_GRANT_USE_CASE.md](PHASE2_GRANT_USE_CASE.md).
- **Close:** "Aligned to NIST AI RMF functions; evidence is exportable and
  reproducible for review."

## If asked "is this production-ready?"
Answer honestly: it is **pilot-ready for evaluation**, not a production-certified
deployment. See *Known limitations* in the runbook (migrations, operator-bypass
hardening, packet persistence). That candor is part of the value.
