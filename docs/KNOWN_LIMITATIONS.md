# Known limitations (Gmail v1 slice)

This document freezes expectations for the current **governed Gmail** slice. It is not a roadmap.

## Product / scope

- **Single Gmail account** per deployment (one token path / one connector configuration).
- **No multi-channel** posting (e.g. YouTube), calendar automation, or broad connector library.
- **No autonomous sending:** outbound delivery requires explicit approval and a worker running `email.send_approved`.
- **No first-class operator UI:** HTTP APIs only; inspection is JSON.

## Classification and policy

- Chat routing uses **keyword heuristics** (`policy_service`, `email_service`), not an LLM. Misclassification is possible; adjust copy or extend classifiers deliberately.
- **Destructive** phrasing in messages is blocked by default; **outbound send** and **publish** require approval.

## Data and tenancy

- `tenant_id` exists on models for future use; isolation guarantees are **not** fully enforced across all code paths—treat as single-tenant until hardened.

## Worker / infrastructure

- **Polling worker** over the database; no Redis/SQS in this slice. Ordering is “oldest pending first.”
- **Idempotency** for enqueue uses `idempotency_key` on jobs (e.g. `email.send:{approval_id}`).

## Gmail / provider

- **Stub mode** does not call Google; IDs are synthetic.
- **Live mode** requires maintained OAuth tokens and correct scopes; provider errors surface as failed jobs and audit entries.
- Thread hints from chat (e.g. `thread=…`) must be valid for your connector mode (stub accepts arbitrary strings; live must match Gmail thread ids).

## Auth

- **Operator API key** is a single shared secret header, not user identity, RBAC, or SSO.
- **`/chat`** is intentionally outside the operator key gate.

## Retry semantics

- Only **`email.send_approved`** jobs in **`failed`** state are retryable via `POST /jobs/{id}/retry`.
- Retries are **blocked** after a successful send is recorded (approval `gmail_message_id` or delivery `sent` + message id). See runbook for exact error strings.

When these limits stop matching your needs, prefer **deepening Gmail + governance** or **porting the same pattern** to another connector rather than expanding scope ad hoc.
