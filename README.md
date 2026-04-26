# codex-control-plane

A **governed execution control plane** for communications: work is ingested as durable jobs, **policy** decides what needs a human gate, **approvals** record decisions, **workers** run only what was approved, and **audit plus domain records** make outcomes inspectable. It is not a general-purpose chatbot, “send it for me” assistant, or silent automation layer.

**Release marker:** tag [`gmail-v1-pattern`](https://github.com/JermaineMerritt-ai/codex-control-plane/tree/gmail-v1-pattern) on `master` — proven **stub-mode** end-to-end path: policy → approval → conditional enqueue → send → delivery record → audit.

---

## Why it exists

Teams need to use AI and automation against real channels (email first) without surprise sends or opaque behavior. This codebase optimizes for **control**: explicit queues, approval where policy requires it, idempotent execution on retries, and a trail you can show to an operator or a reviewer. For the full product stance, see [docs/WHAT_THIS_SYSTEM_IS.md](docs/WHAT_THIS_SYSTEM_IS.md).

---

## The governed execution pattern

Every side-effecting path is designed to follow the same shape:

1. **Intake** — e.g. `POST /chat` → durable `chat.orchestrate` job.  
2. **Policy** — heuristics route to read-only, draft, outbound (approval-gated), etc.  
3. **Approval** (when required) — draft attached to the approval; no send until decision.  
4. **Execution** — `email.send_approved` job after approve; worker performs the send.  
5. **Delivery + audit** — `GET /email/...` and `GET /audit` tie jobs, approvals, and external ids.

Refusals (no silent live mode without credentials, no undifferentiated multi-account “smart” behavior) are intentional; see the docs above.

---

## Gmail as first proof

- **Reference implementation:** Gmail via a connector (stub or live), following [docs/CONNECTOR_STANDARD.md](docs/CONNECTOR_STANDARD.md).  
- **Operators:** [docs/GMAIL_OPERATOR_RUNBOOK.md](docs/GMAIL_OPERATOR_RUNBOOK.md), [docs/OPERATOR_ACCEPTANCE_CHECKLIST.md](docs/OPERATOR_ACCEPTANCE_CHECKLIST.md).  
- **Live setup:** [docs/LIVE_GMAIL_SETUP.md](docs/LIVE_GMAIL_SETUP.md).  
- **Stub vs live:** `GMAIL_MODE=stub` exercises the same API and job flow with fake draft/message ids; `GMAIL_MODE=live` requires `GMAIL_CREDENTIALS_PATH` and proves real Gmail. The `gmail-v1-pattern` tag documents a **stub** run of the full chain; a separate live proof can be its own milestone (e.g. a later tag).

---

## How to run the API and worker

From the repo root (same `DATABASE_URL` in both processes is strongly recommended, e.g. absolute SQLite path):

**Terminal A — API**

```powershell
$env:DATABASE_URL = "sqlite:///C:/path/to/codex-control-plane/local.db"
$env:GMAIL_MODE = "stub"   # or `live` + valid GMAIL_CREDENTIALS_PATH
uvicorn app.main:app --host 127.0.0.1 --port 8010
```

**Terminal B — worker**

```powershell
$env:DATABASE_URL = "sqlite:///C:/path/to/codex-control-plane/local.db"
$env:GMAIL_MODE = "stub"   # match the API
python -m workers.runner
```

Set `OPERATOR_API_KEY` if you use the operator key middleware (see runbook). **Swagger UI:** `http://127.0.0.1:8010/docs` (match your port).

---

## How to run the demo (repeatable)

**PowerShell (Windows):**

```powershell
cd C:\path\to\codex-control-plane
# Optional: $env:OPERATOR_API_KEY = "your-key"
.\scripts\demo_gmail_control_plane.ps1 -ThreadId "YOUR_GMAIL_THREAD_ID" -BaseUrl "http://127.0.0.1:8010"
```

The script walks: health → `POST /chat` → wait for the chat job → find the **matching** pending approval → `POST /approve` → wait for `email.send_approved` → delivery by job id → `GET /audit`, then prints a **FINAL RESULT** block (ids + audit chain for this run). To summarize an existing `email.send_approved` job id, use [scripts/show_run_summary.ps1](scripts/show_run_summary.ps1). Use a real thread id for live Gmail; stub mode still runs the same control-plane steps.

A shell variant lives at [scripts/demo_gmail_flow.sh](scripts/demo_gmail_flow.sh).

**2–3 minute presenter script (what to say + expected outputs):** [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md).

---

## What is intentionally out of scope (for now)

- A full web “dashboard” product UI (the API includes FastAPI `/docs` only).  
- Auto-approve in production, or merging behavior across separate governed contexts/accounts.  
- LLM-in-the-loop as the default decision maker for policy (classifiers are deliberate, conservative heuristics today).  
- Treating this repo as a finished SaaS; it is a **pattern and reference implementation** you extend with the same approval and audit bar.

Deeper “limitations” and boundaries: [docs/KNOWN_LIMITATIONS.md](docs/KNOWN_LIMITATIONS.md). Repo layout: [docs/STRUCTURE.md](docs/STRUCTURE.md).

---

## Develop and test

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

```bash
# Run API (example)
uvicorn app.main:app --reload
```

```bash
pytest
```

---

## License and contributions

Add a `LICENSE` and contribution guidelines when you open the project to collaborators; the governance model above should govern changes to risky paths (policy, approval, send) as well as code.
