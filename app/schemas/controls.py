"""Read schemas for the control/regulation reference catalog (PR 5)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from db.models import Control, ControlFramework, Regulation


class FrameworkResponse(BaseModel):
    id: str
    name: str
    version: str
    description: str | None = None


class ControlResponse(BaseModel):
    id: str
    framework_id: str
    code: str
    title: str
    description: str | None = None


class RegulationResponse(BaseModel):
    id: str
    name: str
    jurisdiction: str | None = None
    description: str | None = None


class FrameworkListResponse(BaseModel):
    items: list[FrameworkResponse] = Field(default_factory=list)


class ControlListResponse(BaseModel):
    items: list[ControlResponse] = Field(default_factory=list)


class RegulationListResponse(BaseModel):
    items: list[RegulationResponse] = Field(default_factory=list)


def framework_to_response(row: ControlFramework) -> FrameworkResponse:
    return FrameworkResponse(
        id=row.id, name=row.name, version=row.version, description=row.description
    )


def control_to_response(row: Control) -> ControlResponse:
    return ControlResponse(
        id=row.id,
        framework_id=row.framework_id,
        code=row.code,
        title=row.title,
        description=row.description,
    )


def regulation_to_response(row: Regulation) -> RegulationResponse:
    return RegulationResponse(
        id=row.id, name=row.name, jurisdiction=row.jurisdiction, description=row.description
    )
