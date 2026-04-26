"""Job inspection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.jobs import JobDetailResponse, job_to_detail
from app.schemas.operator import JobListResponse, job_to_summary
from services.job_service import get_job_by_id, list_jobs, retry_failed_job

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
def list_jobs_api(
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
):
    rows = list_jobs(db, status=status, job_type=job_type, limit=limit)
    return JobListResponse(items=[job_to_summary(j) for j in rows])


@router.post("/{job_id}/retry", response_model=JobDetailResponse)
def retry_job(job_id: str, db: Session = Depends(get_db)):
    try:
        retry_failed_job(db, job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job = get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job_to_detail(job)


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = get_job_by_id(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job_to_detail(job)
