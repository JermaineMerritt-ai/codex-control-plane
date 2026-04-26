# Operator acceptance checklist (live-proven)

Use this **as a new operator** with only the repo, `infra/env.example`, and `docs/`—no tribal knowledge. Goal: **live-proven and patternized** for Gmail v1.

## Preconditions

- [ ] Python 3.11+, `pip install -e ".[dev]"` and `pip install -e ".[gmail]"`
- [ ] Real Gmail OAuth token file; scopes per [LIVE_GMAIL_SETUP.md](LIVE_GMAIL_SETUP.md)
- [ ] `DATABASE_URL` chosen; same value for API and worker
- [ ] `OPERATOR_API_KEY` set for anything network-exposed
- [ ] `GMAIL_MODE=live` and `GMAIL_CREDENTIALS_PATH` set to an **existing** file (expect **immediate startup failure** if wrong—see runbook)

**One governed context at a time:** complete sections B–D for **one** real Gmail account and token first (your primary ops inbox). Only then optionally repeat on a **second** account to observe tone/risk differences—**do not** merge workflows, shared inboxes, or cross-account automation until per-context policy exists. See [WHAT_THIS_SYSTEM_IS.md](WHAT_THIS_SYSTEM_IS.md).

## A. Documentation smoke test

- [ ] [GMAIL_OPERATOR_RUNBOOK.md](GMAIL_OPERATOR_RUNBOOK.md) is enough to start API + worker without asking the author
- [ ] [LIVE_GMAIL_SETUP.md](LIVE_GMAIL_SETUP.md) matches what you had to do for OAuth/token (note gaps in the doc, not only in your head)
- [ ] [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md) matches what you observed

## B. Happy path (live)

Run exactly as documented; prefer **`scripts/demo_gmail_flow.sh`** from repo root with `PYTHONPATH=.` (or equivalent manual curls from the runbook).

- [ ] `POST /chat` with outbound wording + thread hint returns `job_id`
- [ ] Worker processes `chat.orchestrate`; `GET /approvals?status=pending` shows a row with outbound context
- [ ] `POST /approvals/{id}/approve` returns `execution_job_id` when Gmail outbound gate is satisfied
- [ ] Worker processes `email.send_approved`
- [ ] `GET /email/deliveries` shows terminal state (`sent` in live, or `failed` with `last_error` if provider failed)
- [ ] `GET /audit` shows approval + enqueue + success/failure events
- [ ] In Gmail UI: draft existed pre-approve; after success, sent message matches expectation (or failure is explained by job/audit)

## C. Failure / retry path (live or stub)

Pick **one** path and complete it deliberately:

**Option 1 — live failure:** induce a failing send (e.g. invalid draft id after manual delete, or revoked token), then:

- [ ] Job `email.send_approved` is `failed` with a clear `last_error`
- [ ] `GET /email/deliveries` and `GET /audit` explain what happened
- [ ] `POST /jobs/{id}/retry` **only if** rules allow (see runbook); if send **already recorded**, confirm retry returns **blocked** (`retry_blocked_*`)

**Option 2 — stub blocked retry:** in `GMAIL_MODE=stub`, mark approval with `gmail_message_id` (or delivery `sent`) per tests/runbook, failed job present:

- [ ] `POST /jobs/{id}/retry` returns **400** with `retry_blocked_already_sent` or `retry_blocked_delivery_sent`

## D. Security checks

- [ ] With `OPERATOR_API_KEY` set, `GET /jobs` without header returns **401**
- [ ] With correct `X-Operator-Key`, operator routes return **200**
- [ ] `/health` and `/chat` work without operator key (by design); confirm edge protection if API is public

## E. Freeze the pattern

When A–D pass:

- [ ] Tag or branch this revision as **reference governed connector** (e.g. `gmail-v1-pattern` or release tag)
- [ ] File any doc fixes as a small follow-up PR—**do not** expand product scope in the same change

## Sign-off

| Item | Operator | Date |
|------|----------|------|
| Docs sufficient | | |
| Live happy path | | |
| Failure/retry path | | |
| Pattern tagged | | |
