# Release notes — Gmail governed slice v1

**Scope:** Single-account Gmail workflow with policy, explicit approval, audited send, durable inspection, and operator recovery—not a multi-connector or social product.

## What shipped

- **Intake:** `POST /chat` → durable `chat.orchestrate` job.
- **Policy:** Keyword classification → allow / block / require approval (`services/policy_service.py`).
- **Email workflow:** Read thread, draft, outbound gate with **`email.outbound`** approval payload (`gmail_draft_id`, workflow discriminator).
- **Execution:** `email.send_approved` worker job; Gmail stub or live via **`GMAIL_MODE`** + **`GMAIL_CREDENTIALS_PATH`**.
- **Persistence:** `EmailThreadRecord`, `EmailDeliveryRecord` for operator-visible state.
- **Governance:** Append-only audit (`approval.*`, `email.send_approved.*`).
- **Idempotency:** `email.send:{approval_id}`; send dedupe via approval `gmail_message_id` / delivery row.
- **Operator API:** `/jobs`, `/approvals`, `/audit`, `/email/*`; optional **`OPERATOR_API_KEY`** / **`X-Operator-Key`**.
- **Retry:** `POST /jobs/{id}/retry` for failed `email.send_approved` only, with explicit **blocked** rules when already sent or rejected.
- **Safety:** Live Gmail misconfiguration **fails at startup** (settings validation)—no silent stub fallback.
- **Docs:** Runbook, live setup, known limitations, connector standard, acceptance checklist, demo script.
- **Tests:** Stub-path coverage, operator auth, email inspection APIs, retry blocks, settings validation; opt-in live integration module.

## Operator entrypoints

| Doc / asset | Purpose |
|-------------|---------|
| [WHAT_THIS_SYSTEM_IS.md](WHAT_THIS_SYSTEM_IS.md) | Strategic positioning (non-technical) |
| [GMAIL_OPERATOR_RUNBOOK.md](GMAIL_OPERATOR_RUNBOOK.md) | Day-to-day operations |
| [LIVE_GMAIL_SETUP.md](LIVE_GMAIL_SETUP.md) | OAuth, scopes, env |
| [OPERATOR_ACCEPTANCE_CHECKLIST.md](OPERATOR_ACCEPTANCE_CHECKLIST.md) | Live proof + sign-off |
| [CONNECTOR_STANDARD.md](CONNECTOR_STANDARD.md) | Pattern for the **next** connector |
| [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) | Boundaries |
| `scripts/demo_gmail_flow.sh` | Repeatable happy path |
| `infra/env.example` | Env template |

## Upgrade / compatibility

- **Breaking:** None versioned yet; treat as **v0.1.x / v1 slice** tag on git for freeze points.
- **Env:** `GMAIL_MODE=live` now **requires** existing `GMAIL_CREDENTIALS_PATH` file or process will not start.

## What is explicitly out of scope

YouTube, multi-platform posting, autonomous outbound, heavy UI, broad connector library, enterprise IAM—see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).

## Suggested git freeze

After completing [OPERATOR_ACCEPTANCE_CHECKLIST.md](OPERATOR_ACCEPTANCE_CHECKLIST.md), tag this commit, e.g. **`gmail-v1-pattern`** or **`v0.1.0-gmail`**, and treat it as the reference implementation for [CONNECTOR_STANDARD.md](CONNECTOR_STANDARD.md).
