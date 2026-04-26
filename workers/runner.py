"""Minimal polling worker: claim pending jobs, dispatch, record failures."""

from __future__ import annotations

import logging
import time
from typing import Any

import workers.tasks  # noqa: F401 — register handlers
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from db.models import Job
from services.job_service import claim_next_pending, mark_job_failed
from workers.tasks import run_task

logger = logging.getLogger(__name__)


def process_job(session: Session, job: Job) -> dict[str, Any]:
    """Execute task handler; on failure, persist job error state."""
    try:
        outcome = run_task(session, job)
    except Exception as exc:  # noqa: BLE001 — worker boundary; persist message
        logger.exception("job_id=%s handler raised", job.id)
        session.refresh(job)
        mark_job_failed(session, job, str(exc))
        return {"ok": False, "error": str(exc)}
    if not outcome.get("ok"):
        err = outcome.get("error", "task_failed")
        logger.error("job_id=%s task reported failure: %s", job.id, err)
        session.refresh(job)
        mark_job_failed(session, job, err)
        return outcome
    return outcome


def poll_once(engine: Engine) -> bool:
    """Process at most one pending job. Returns True if work was done."""
    from app.config import get_settings

    get_settings()
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with factory() as session:
        job = claim_next_pending(session)
        if job is None:
            return False
        logger.info("claimed job_id=%s type=%s", job.id, job.type)
        process_job(session, job)
    return True


def run_forever(engine: Engine, *, poll_interval_sec: float = 2.0) -> None:
    """Long-running loop for local/dev until real queue infra lands."""
    logging.basicConfig(level=logging.INFO)
    logger.info("runner started poll_interval_sec=%s", poll_interval_sec)
    while True:
        try:
            worked = poll_once(engine)
        except Exception:  # noqa: BLE001
            logger.exception("poll_once failed")
            worked = False
        if not worked:
            time.sleep(poll_interval_sec)


if __name__ == "__main__":
    from app.config import get_settings
    from db.session import get_engine

    get_settings()
    run_forever(get_engine())
