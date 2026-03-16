from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select

from src.adapters.db import db_session
from src.api.routes.auth import AuthUser, get_current_user
from src.domain.models import ModuleProgress

router = APIRouter(prefix="/progress", tags=["progress"])


class ModuleProgressResponse(BaseModel):
    module_id: str = Field(..., description="Module id (uuid)")
    started_at: datetime | None = Field(default=None, description="When module was started")
    completed_at: datetime | None = Field(default=None, description="When module was completed")
    exam_attempt_id: str | None = Field(default=None, description="Associated exam attempt id")
    exam_passed: bool = Field(..., description="Whether module exam was passed")


@router.get(
    "/modules/{module_id}",
    response_model=ModuleProgressResponse,
    summary="Get progress for a module",
    description="Returns module progress and exam pass flag.",
)
def get_module_progress(module_id: str, user: AuthUser = Depends(get_current_user)) -> ModuleProgressResponse:
    with db_session() as session:
        row = session.execute(
            select(ModuleProgress).where(ModuleProgress.user_id == user.user_id).where(ModuleProgress.module_id == module_id)
        ).scalar_one_or_none()
        if not row:
            return ModuleProgressResponse(module_id=module_id, started_at=None, completed_at=None, exam_attempt_id=None, exam_passed=False)

        return ModuleProgressResponse(
            module_id=module_id,
            started_at=row.started_at,
            completed_at=row.completed_at,
            exam_attempt_id=str(row.exam_attempt_id) if row.exam_attempt_id else None,
            exam_passed=bool(row.exam_passed),
        )
