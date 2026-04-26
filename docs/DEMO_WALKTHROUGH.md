# 3-minute demo walkthrough (Gmail stub pattern)

Use this when you need someone to **see** the governed path without reading the codebase. For release pins, see tag **`gmail-v1-pattern`** (proof commit) and **`docs-readme-v1`** (README + entry).

## What you will show

1. Work enters as a **chat job**; policy requires **approval** before send.  
2. Operator sees **pending approval** with **draft + workflow** in the payload.  
3. After **approve**, a **send job** runs; **delivery** and **audit** record the outcome.  
4. Nothing sends until step 3.

Stub mode uses fake `draft:stub:` / `msg:stub:` ids; live mode uses real Gmail with the same API shape.

## Preconditions (two terminals + same DB)

From repo root, use one **absolute** SQLite URL in **both** processes:

```powershell
$env:DATABASE_URL = "sqlite:///C:/path/to/codex-control-plane/local.db"
$env:GMAIL_MODE = "stub"
```

**Terminal A — API**

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

**Terminal B — worker**

```powershell
python -m workers.runner
```

In Terminal B you should see lines like `claimed job_id=... type=chat.orchestrate` when work is pending.

Optional: `OPERATOR_API_KEY` on the API process if you use operator auth; pass the same to script via `$env:OPERATOR_API_KEY`.

## Run the demo (Terminal C)

Replace the thread id with a real Gmail thread id for live tests; stub still exercises the control plane.

```powershell
cd C:\path\to\codex-control-plane
.\scripts\demo_gmail_control_plane.ps1 -ThreadId "YOUR_THREAD_ID" -BaseUrl "http://127.0.0.1:8010"
```

## Expected output (high level)

| Step | What appears |
|------|----------------|
| Health | `OK: .../health` |
| Chat | `Chat job_id: <uuid>` |
| Orchestrate | `Chat orchestration succeeded.` |
| Approval | `Pending approval_id ... (for this /chat only)` |
| Detail JSON | `gmail_draft_id`, `workflow: "email.outbound"`, `thread_hint` |
| Approve | `execution_job_id: <uuid>` |
| Send job | `type: email.send_approved`, `status: succeeded` |
| Result | Stub: `"Outbound message sent (stub)."` and `gmail.message` artifact |
| Delivery | `"status": "sent"` (with stub or real message id) |
| Audit | Rows including `approval.created`, `approval.approved`, `email.send_approved.enqueued`, `email.send_approved.succeeded` for this run |

If step 1b or 4 hangs, the **worker** is not running or **DATABASE_URL** does not match the API.

## Narration (what to say in 2–3 minutes)

1. *“Every outbound send starts as a job; we don’t touch Gmail send in the request path.”*  
2. *“Policy classified this as outbound; the system created a draft and a pending approval — that’s the gate.”*  
3. *“I approve; the worker picks up `email.send_approved` only after that.”*  
4. *“Delivery and audit are the receipts: you can answer what was approved and what ran.”*

## After the demo

- Stub proof is enough to show **governance**; say that **live** is the same pipeline with OAuth and real ids.  
- Point viewers to [README.md](../README.md) and [GMAIL_OPERATOR_RUNBOOK.md](GMAIL_OPERATOR_RUNBOOK.md).
