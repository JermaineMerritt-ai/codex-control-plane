# Live Gmail setup

How to run the control plane against a **real** Gmail account (single user / single token).

## 1. Install API dependencies

```bash
pip install -e ".[gmail]"
```

This adds `google-api-python-client`, `google-auth-oauthlib`, and related libraries.

## 2. OAuth client and token JSON

You need a **Google Cloud OAuth 2.0 Client ID** (Desktop or Web) with the Gmail API enabled for the project.

Typical steps:

1. In [Google Cloud Console](https://console.cloud.google.com/), create or select a project.
2. Enable **Gmail API**.
3. Configure OAuth consent screen (test users if in testing).
4. Create **OAuth client ID** credentials; download client secrets JSON if you use an installed-app flow.
5. Run an OAuth flow (outside this repo’s scope) to obtain **refreshed user credentials** and save them as a **token JSON** file the app can load.

The exact file format must match what `connectors/gmail_live.py` expects via `google.oauth2.credentials.Credentials.from_authorized_user_file` (authorized user JSON with `token`, `refresh_token`, `client_id`, `client_secret`, etc., as produced by common OAuth examples).

**Scopes:** the code requests at minimum (see `connectors/gmail_live.py`):

- `https://www.googleapis.com/auth/gmail.readonly`
- `https://www.googleapis.com/auth/gmail.compose`

Re-authorize if your token was minted with narrower scopes.

## 3. Environment

```bash
export GMAIL_MODE=live
export GMAIL_CREDENTIALS_PATH=/absolute/path/to/token.json
```

Rules enforced by the app:

- If `GMAIL_MODE=live`, **`GMAIL_CREDENTIALS_PATH` must be set and must point to an existing file** or the API/worker **will not start** (validation runs when settings load).
- There is **no silent fallback** to stub when live is configured.

Copy variable names from `infra/env.example`.

## 4. Run API and worker

Use the **same** `DATABASE_URL`, `GMAIL_MODE`, and `GMAIL_CREDENTIALS_PATH` for both processes.

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m workers.runner
```

## 5. Prove connectivity

**Automated (optional):**

```bash
export GMAIL_INTEGRATION_TEST=1
export GMAIL_TEST_THREAD_ID=<real Gmail thread id>
pytest tests/test_gmail_live_integration.py -v
```

**Manual:** follow [GMAIL_OPERATOR_RUNBOOK.md](GMAIL_OPERATOR_RUNBOOK.md) and `scripts/demo_gmail_flow.sh` with live env; confirm a draft appears in Gmail and, after approval, a sent message (or provider error recorded on the job).

## 6. Security notes

- Treat `token.json` like a password: file permissions, no commits, no logs.
- Set **`OPERATOR_API_KEY`** so `/jobs`, `/approvals`, `/audit`, and `/email` are not open on a network-facing deployment.
- `/chat` remains unauthenticated by design (add your own edge auth if exposed).

## 7. Troubleshooting

| Issue | What to check |
|-------|----------------|
| `invalid_grant` / refresh errors | Regenerate token; clock skew; revoked consent. |
| 403 / insufficientPermissions | Token missing scopes; re-authorize with correct scopes. |
| File not found at startup | Path typo; process cwd differs; use absolute path. |
| Draft created but send fails | Send uses draft id from create step; check Gmail quotas and draft still exists. |
