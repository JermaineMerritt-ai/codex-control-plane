# Gmail operator runbook

Operational guide for the governed Gmail slice (single account, approval-gated send).

## Prerequisites

- Python 3.11+
- Install: `pip install -e ".[dev]"` and, for live Gmail, `pip install -e ".[gmail]"`
- Same `DATABASE_URL` for the API process and the worker (shared SQLite file or Postgres)

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `DATABASE_URL` | Recommended | Defaults to `sqlite:///./local.db`. Must match API and worker. |
| `GMAIL_MODE` | No | `stub` (default) or `live`. |
| `GMAIL_CREDENTIALS_PATH` | If `GMAIL_MODE=live` | Path to OAuth **user** token JSON (file must exist; app/worker fail at startup if missing). |
| `OPERATOR_API_KEY` | **Strongly recommended** for any shared/real use | If set, `/jobs`, `/approvals`, `/audit`, and `/email` require header `X-Operator-Key: <value>`. `/health` and `/chat` stay open. FastAPI `/docs` and `/openapi.json` are **not** gated—disable or protect at the edge in production. |

See also: [WHAT_THIS_SYSTEM_IS.md](WHAT_THIS_SYSTEM_IS.md) (strategic positioning), [LIVE_GMAIL_SETUP.md](LIVE_GMAIL_SETUP.md), [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md), [OPERATOR_ACCEPTANCE_CHECKLIST.md](OPERATOR_ACCEPTANCE_CHECKLIST.md) (live proof), [CONNECTOR_STANDARD.md](CONNECTOR_STANDARD.md) (pattern for future connectors), [RELEASE_NOTES_GMAIL_V1.md](RELEASE_NOTES_GMAIL_V1.md).

## Run the API

From the repo root:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

On first request, settings load: **`GMAIL_MODE=live` without a valid credentials file prevents startup** (no silent fallback to stub).

## Run the worker

The worker polls the DB for pending jobs (same `DATABASE_URL`):

```bash
python -m workers.runner
```

Each poll validates settings (so live misconfiguration is caught before processing email jobs).

For ad-hoc processing (e.g. demos), you can run one poll from Python (see `scripts/demo_gmail_flow.sh`).

## Stub vs live Gmail

| Mode | Behavior |
|------|----------|
| `stub` | Read/draft/send return synthetic IDs (`draft:stub:…`, `msg:stub:…`). Safe for CI and local flow testing. |
| `live` | Uses Google Gmail API with the token at `GMAIL_CREDENTIALS_PATH`. Requires `[gmail]` extras and a real OAuth token file. |

Switching modes: set env, restart API and worker. Do not mix different `GMAIL_MODE` values across processes that share one DB.

## Happy path: read / draft / approve / send

### Outbound send (approval-gated)

1. **Intake:** `POST /chat` with a message that triggers **outbound** policy, e.g. contains `send email` (see `services/policy_service.py`).
2. **Worker:** Run the worker once; `chat.orchestrate` creates an approval, creates a Gmail **draft**, and records an `EmailDeliveryRecord` in `awaiting_approval`.
3. **Inspect:** `GET /approvals?status=pending` (with operator key if configured). Note `approval_id` and optional `execution_job_id` after approval.
4. **Approve:** `POST /approvals/{id}/approve` with body `{"actor":"…","note":"…"}`. This enqueues `email.send_approved` if the approval carries `gmail_draft_id` and `workflow: email.outbound`.
5. **Worker:** Run the worker again; it sends the draft (stub or live) and updates delivery + approval with `gmail_message_id`.

### Inbox read (no send)

Use phrasing that maps to **read_only** policy (e.g. `list my emails`, `show thread`) and include a **thread hint** if needed, e.g. `thread=abc123` in the message. With `status: completed`, the worker persists a thread snapshot when the intent is inbox read.

A repeatable curl + worker sequence is in **`scripts/demo_gmail_flow.sh`**.

## Operator inspection

All routes below require `X-Operator-Key` when `OPERATOR_API_KEY` is set.

| Endpoint | Use |
|----------|-----|
| `GET /jobs` | List jobs; filter `?status=failed` etc. |
| `GET /jobs/{job_id}` | Job detail + payload. |
| `POST /jobs/{job_id}/retry` | Retry a **failed** `email.send_approved` job only (see retry rules). |
| `GET /approvals` | List approvals. |
| `GET /approvals/{id}` | Approval payload (draft id, workflow, decision). |
| `GET /audit` | Audit timeline. |
| `GET /email/deliveries` | Deliveries; `?status=sent|failed|awaiting_approval`. |
| `GET /email/deliveries/by-approval/{approval_id}` | One delivery row. |
| `GET /email/deliveries/by-job/{job_id}` | By **execution** job id (`email.send_approved`). |
| `GET /email/threads/{external_thread_id}/summary` | Thread + related deliveries. |

## Retry failed sends

- **Allowed:** `POST /jobs/{job_id}/retry` when job type is `email.send_approved`, status is `failed`, and send is **not** already recorded.
- **Blocked (HTTP 400):**
  - `retry_blocked_approval_rejected` — need a new approval flow, not a blind retry.
  - `retry_blocked_already_sent` — approval payload already has `gmail_message_id`.
  - `retry_blocked_delivery_sent` — `EmailDeliveryRecord` is `sent` with a message id.
- Other failures: `job_not_retryable`, `job_not_failed`, `job_not_found`.

Rules are enforced in `services/job_service.py` (`_assert_email_send_retry_allowed`).

## Common errors

| Symptom | Likely cause |
|---------|----------------|
| App/worker exits on start with Gmail message | `GMAIL_MODE=live` but missing/invalid `GMAIL_CREDENTIALS_PATH`. |
| `401` on `/jobs` etc. | `OPERATOR_API_KEY` set; add `X-Operator-Key`. |
| `400` on approve | Invalid approval state, missing `gmail_draft_id`, or gate validation failed (`approval_wrong_workflow`, etc.). |
| Chat job succeeds but no draft | Message did not classify as outbound + approval path; check policy keywords. |
| Send job fails (live) | OAuth scopes, expired token, or Gmail API error; check job `last_error` and `audit`. |

## What is intentionally blocked

- **Unapproved send:** connector `send_message` without `approved=True` raises (gated send path only).
- **Retry after success:** prevents double send; use audit + delivery rows to confirm idempotency.
- **Destructive phrasing** in chat classifier routes to blocked policy (no approval queue).

For scope boundaries and known gaps, see [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
