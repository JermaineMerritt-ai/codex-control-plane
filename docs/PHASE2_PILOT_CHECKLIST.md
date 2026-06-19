# Phase 2 Pilot Launch Checklist

For running a guided 30–60 day pilot on the merged Phase 2 control plane.
CodexDominion **supports audit readiness, evidence collection, and governance
workflows**; it does not certify, guarantee, or determine compliance.

## Pre-pilot (environment)
- [ ] Repo installed; `pytest` green (121 passed, 2 skipped).
- [ ] `DATABASE_URL` chosen and used for **both** seed and API (a dedicated DB).
- [ ] API run **without** `OPERATOR_API_KEY` (console uses `X-Api-Key` RBAC), or
      `REQUIRE_RBAC_FOR_OPERATOR=true` with provisioned principals if hardening.
- [ ] `python -m scripts.seed_pilot` run; `/console` loads; `/health` ok.
- [ ] **Demo keys rotated** if the pilot is shared beyond a local machine.

## Pilot setup (buyer)
- [ ] One executive or compliance **sponsor** identified.
- [ ] Two stakeholder sessions scheduled.
- [ ] A real set of AI/vendor/automation use cases chosen for review.
- [ ] Per-role principals provisioned (Admin/Operator/Reviewer/Auditor) — replace
      demo users/keys with the buyer's own.

## During the pilot (the loop, per use case)
- [ ] Operator submits each governance review.
- [ ] Policy + deterministic risk recorded; medium/high routed to approval.
- [ ] Reviewer approves/rejects (separation of duties enforced).
- [ ] Audit trail recorded and verifiable (`/audit/verify`).
- [ ] Controls/regulations mapped per action.
- [ ] Evidence packet exported (JSON + Markdown) per use case.
- [ ] Evidence **gaps** reviewed and tracked.

## Exit / readout
- [ ] Executive readout: governed actions, approvals, risk distribution, audit
      verification status, mapped controls, exported packets, gaps.
- [ ] Buyer agrees the loop reduces audit/exam/review prep effort.
- [ ] Decision on continuation; capture v-next signals (persistence, more
      connectors, per-tenant chain anchoring, UI depth).

## Guardrails (do not over-promise)
- [ ] No claims of guaranteed compliance, certification, or regulatory approval.
- [ ] "Pilot-ready for evaluation," not production-certified.
- [ ] Not-production-grade items disclosed (migrations, operator-bypass hardening,
      packet persistence, audit anchoring) — see [PHASE2_RUNBOOK.md](PHASE2_RUNBOOK.md).
