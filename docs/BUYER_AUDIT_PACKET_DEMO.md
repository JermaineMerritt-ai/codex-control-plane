# Buyer-Facing Audit Packet Demo

A short, honest walkthrough that produces the artifact a procurement officer,
compliance lead, auditor, or pilot customer can actually read: an **evidence
packet** for one governed action, exported as JSON and Markdown.

This demo **supports audit readiness, evidence collection, and governance
workflows.** It does not certify, guarantee, or determine compliance, and is not
a regulatory authorization. It runs in stub mode with no live Gmail.

## What the demo shows (the chain)

```
AI System → Workflow → Governed Action → Policy Decision → Approval
  → Execution → Audit Event → Control Mapping → Regulation → Evidence Artifact
```

…then assembles that chain into an **evidence packet** and exports it in two
formats. Every step uses existing services/endpoints — no new product behavior,
no hidden automation.

## Run it (no server, no Gmail required)

```bash
python -m scripts.demo_evidence_packet
```

The helper uses a throwaway SQLite database, seeds the RBAC roles and the control
catalog, builds one complete governed-action chain, and prints:

1. the **executive summary**,
2. the **evidence packet as JSON**,
3. the **evidence packet as Markdown**.

It writes nothing to your working database and never contacts Gmail.

## What to point at (2–3 minutes)

1. **Governed action + policy decision** — "this action was governed; policy said
   it required approval (`requires_approval`)."
2. **Approval + execution** — "a person approved it; execution is linked to the
   approved decision, not a silent send."
3. **Audit events + chain verification** — "every step is on a tamper-evident
   hash chain; the packet shows the verification result."
4. **Control + regulation mapping** — "the action is mapped to a control in a
   recognized framework, with the regulation noted."
5. **Evidence artifact** — "supporting evidence is attached to the action."
6. **Evidence gaps** — "the packet is honest about what's missing; a complete
   chain reports no gaps, an incomplete one lists them."
7. **JSON + Markdown export** — "hand the JSON to a system, the Markdown to a
   human."

## Live API equivalent

With the API running (see the README), the same packet is available over HTTP,
tenant-scoped and `view_audit`-gated:

```
GET /evidence/packets/action/{governed_action_id}
GET /evidence/packets/workflow/{workflow_id}
GET /evidence/packets/export/{governed_action_id}?format=json   # or format=md
```

A caller can only retrieve packets for its own tenant; another tenant's packet
returns 404, and a principal without `view_audit` is denied.

## Honest framing for buyers

- This is a **pattern and reference implementation**, pilot-ready for evaluation,
  not a finished or production-certified product. See
  [ENTERPRISE_GOVERNANCE_FOUNDATION.md](ENTERPRISE_GOVERNANCE_FOUNDATION.md) for
  the security model, remaining limitations, and what is not yet production-grade.
- The evidence packet is a governance and audit-readiness artifact. It records
  what happened and what evidence exists; it does not assert that any regulatory
  obligation has been met.
