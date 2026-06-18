"""Job inspection routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_current_tenant_id, get_db, require_permission
from app.schemas.jobs import JobDetailResponse, job_to_detail
from app.schemas.operator import JobListResponse, job_to_summary
from services.job_service import get_job_by_id, list_jobs, retry_failed_job
from services.rbac_service import Principal

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=JobListResponse)
def list_jobs_api(
    db: Session = Depends(get_db),
    tenant_id: str | None = Depends(get_current_tenant_id),
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=50, ge=1, le=200),
):
    rows = list_jobs(db, status=status, job_type=job_type, tenant_id=tenant_id, limit=limit)
    return JobListResponse(items=[job_to_summary(j) for j in rows])


@router.post("/{job_id}/retry", response_model=JobDetailResponse)
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(require_permission("execute_approved_action")),
):
    try:
        retry_failed_job(db, job_id, tenant_id=principal.tenant_id)
    except ValueError as exc:
        # Cross-tenant / missing job => 404 (non-leaking); other failures => 400.
        status = 404 if str(exc) == "job_not_found" else 400
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    job = get_job_by_id(db, job_id, tenant_id=principal.tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job_to_detail(job)


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: str | None = Depends(get_current_tenant_id),
):
    job = get_job_by_id(db, job_id, tenant_id=tenant_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job_to_detail(job)
