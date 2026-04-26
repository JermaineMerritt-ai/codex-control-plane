#!/usr/bin/env bash
# Repeatable happy path: chat (outbound) -> worker -> approve -> worker -> inspect.
#
# Prerequisites:
#   - API running (e.g. uvicorn app.main:app --port 8000)
#   - Same DATABASE_URL as this script's worker polls
#   - From repo root: export PYTHONPATH=.
#
# Usage:
#   BASE_URL=http://127.0.0.1:8000 ./scripts/demo_gmail_flow.sh
#   OPERATOR_API_KEY=secret BASE_URL=http://127.0.0.1:8000 ./scripts/demo_gmail_flow.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="${PYTHONPATH:-}${PYTHONPATH:+:}."

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
CURL_AUTH=()
if [[ -n "${OPERATOR_API_KEY:-}" ]]; then
  CURL_AUTH=(-H "X-Operator-Key: ${OPERATOR_API_KEY}")
fi

poll_worker() {
  python -c "from db.session import get_engine; from workers.runner import poll_once; poll_once(get_engine())"
}

echo "== 1) POST /chat (outbound: triggers approval + draft) =="
CHAT_JSON="$(curl -sS -X POST "${BASE_URL}/chat" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"demo-session","message":"send email thread=demo-thread please: Hello from demo_gmail_flow","max_steps":4}')"
echo "${CHAT_JSON}"
CHAT_JOB="$(echo "${CHAT_JSON}" | python -c "import json,sys; print(json.load(sys.stdin)['job_id'])")"
echo "    chat job_id=${CHAT_JOB}"

echo "== 2) Worker poll (chat.orchestrate) =="
poll_worker

echo "== 3) Pending approvals =="
APPROVALS_JSON="$(curl -sS "${CURL_AUTH[@]}" "${BASE_URL}/approvals?status=pending&limit=5")"
echo "${APPROVALS_JSON}" | python -m json.tool
APPROVAL_ID="$(echo "${APPROVALS_JSON}" | python -c "import json,sys; d=json.load(sys.stdin); i=(d.get('items') or []); print(i[0]['id'] if i else '')")"
if [[ -z "${APPROVAL_ID}" ]]; then
  echo "ERROR: no pending approval. Check GET ${BASE_URL}/jobs/${CHAT_JOB} and policy/outbound wording." >&2
  exit 1
fi
echo "    approval_id=${APPROVAL_ID}"

echo "== 4) POST /approvals/{id}/approve (enqueues email.send_approved) =="
curl -sS -X POST "${BASE_URL}/approvals/${APPROVAL_ID}/approve" \
  "${CURL_AUTH[@]}" \
  -H "Content-Type: application/json" \
  -d '{"actor":"demo-operator","note":"demo_gmail_flow approve"}' | python -m json.tool

echo "== 5) Worker poll (email.send_approved) =="
poll_worker

echo "== 6) Inspect jobs, deliveries, audit (last 5–10) =="
curl -sS "${CURL_AUTH[@]}" "${BASE_URL}/jobs?limit=5" | python -m json.tool
curl -sS "${CURL_AUTH[@]}" "${BASE_URL}/email/deliveries?limit=5" | python -m json.tool
curl -sS "${CURL_AUTH[@]}" "${BASE_URL}/audit?limit=10" | python -m json.tool

echo "== Done. Failure/retry demo: find a failed email.send_approved job_id, then: =="
echo "    curl -X POST ${BASE_URL}/jobs/<job_id>/retry -H 'X-Operator-Key: ...'"
