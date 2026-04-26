"""
Manual / CI integration checks against a real Gmail account.

Requires:
  pip install -e ".[gmail]"
  GMAIL_INTEGRATION_TEST=1
  GMAIL_CREDENTIALS_PATH=/path/to/token.json
  GMAIL_TEST_THREAD_ID=<real Gmail thread id>   # for read test

Optional:
  GMAIL_TEST_CREATE_DRAFT=1  # creates a real draft (side effect)

This module is skipped by default so normal `pytest` stays offline.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("GMAIL_INTEGRATION_TEST") != "1",
    reason="Set GMAIL_INTEGRATION_TEST=1 and GMAIL_CREDENTIALS_PATH to run live Gmail checks",
)


@pytest.mark.integration
def test_live_read_thread_real():
    from connectors.gmail import GmailConfig, GmailConnector

    path = os.environ.get("GMAIL_CREDENTIALS_PATH")
    tid = os.environ.get("GMAIL_TEST_THREAD_ID")
    assert path and tid, "GMAIL_CREDENTIALS_PATH and GMAIL_TEST_THREAD_ID required"

    g = GmailConnector(GmailConfig(mode="live", credentials_path=path))
    out = g.read_thread(tid)
    assert out.get("thread_id") == tid
    assert "snippet" in out


@pytest.mark.integration
def test_live_create_draft_optional():
    if os.environ.get("GMAIL_TEST_CREATE_DRAFT") != "1":
        pytest.skip("Set GMAIL_TEST_CREATE_DRAFT=1 to create a real draft")

    from connectors.gmail import GmailConfig, GmailConnector

    path = os.environ["GMAIL_CREDENTIALS_PATH"]
    g = GmailConnector(GmailConfig(mode="live", credentials_path=path))
    did = g.create_draft(thread_id=None, subject="[integration] codex-control-plane", body="test body")
    assert did
    assert not did.startswith("draft:stub:")
