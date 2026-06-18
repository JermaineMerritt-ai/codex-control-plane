"""Read-only endpoints for the control/regulation reference catalog (PR 5).

This catalog is non-tenant, non-sensitive reference data (publicly known
framework structures), so these reads are not permission-gated. They expose no
tenant or customer data and make no compliance claims.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.deps import get_db
from app.schemas.controls import (
    ControlListResponse,
    FrameworkListResponse,
    RegulationListResponse,
    control_to_response,
    framework_to_response,
    regulation_to_response,
)
from services import control_catalog

router = APIRouter(prefix="/controls", tags=["controls"])


@router.get("/frameworks", response_model=FrameworkListResponse)
def list_frameworks(db: Session = Depends(get_db)):
    rows = control_catalog.list_frameworks(db)
    return FrameworkListResponse(items=[framework_to_response(r) for r in rows])


@router.get("/frameworks/{framework_id}/controls", response_model=ControlListResponse)
def list_framework_controls(framework_id: str, db: Session = Depends(get_db)):
    if control_catalog.get_framework(db, framework_id) is None:
        raise HTTPException(status_code=404, detail="framework_not_found")
    rows = control_catalog.list_controls(db, framework_id)
    return ControlListResponse(items=[control_to_response(r) for r in rows])


@router.get("/regulations", response_model=RegulationListResponse)
def list_regulations(db: Session = Depends(get_db)):
    rows = control_catalog.list_regulations(db)
    return RegulationListResponse(items=[regulation_to_response(r) for r in rows])
