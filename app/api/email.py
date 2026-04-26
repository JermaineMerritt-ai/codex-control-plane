"""Email thread and delivery inspection for operators."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.email_operator import (
    EmailDeliveryDetailResponse,
    EmailDeliveryListResponse,
    ThreadSummaryResponse,
    delivery_to_detail,
)
from services import email_persistence

router = APIRouter(prefix="/email", tags=["email"])


@router.get("/deliveries", response_model=EmailDeliveryListResponse)
def list_deliveries(
    db: Session = Depends(get_db),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    rows = email_persistence.list_deliveries(db, status=status, limit=limit)
    return EmailDeliveryListResponse(items=[delivery_to_detail(r) for r in rows])


@router.get("/deliveries/by-approval/{approval_id}", response_model=EmailDeliveryDetailResponse)
def get_delivery_by_approval(approval_id: str, db: Session = Depends(get_db)):
    row = email_persistence.get_delivery_by_approval_id(db, approval_id)
    if row is None:
        raise HTTPException(status_code=404, detail="delivery_not_found")
    return delivery_to_detail(row)


@router.get("/deliveries/by-job/{job_id}", response_model=EmailDeliveryDetailResponse)
def get_delivery_by_job(job_id: str, db: Session = Depends(get_db)):
    row = email_persistence.get_delivery_by_execution_job_id(db, job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="delivery_not_found")
    return delivery_to_detail(row)


@router.get("/threads/{external_thread_id}/summary", response_model=ThreadSummaryResponse)
def thread_summary(
    external_thread_id: str,
    db: Session = Depends(get_db),
    tenant_id: str | None = Query(default=None),
):
    snap = email_persistence.get_thread_summary(
        db, tenant_id=tenant_id, external_thread_id=external_thread_id
    )
    return ThreadSummaryResponse(thread=snap.get("thread"), deliveries=snap.get("deliveries", []))
