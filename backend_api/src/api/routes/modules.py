from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.adapters.db import db_session
from src.api.routes.auth import get_current_user
from src.api.schemas import ModuleSummary
from src.domain.models import Module

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/modules", tags=["modules"])


@router.get(
    "",
    response_model=list[ModuleSummary],
    summary="List modules",
    description="Returns published modules for the authenticated user.",
)
def list_modules(_: dict = Depends(get_current_user)) -> list[ModuleSummary]:
    with db_session() as session:
        modules = (
            session.execute(select(Module).where(Module.is_published.is_(True)).order_by(Module.sort_order.asc()))
            .scalars()
            .all()
        )
        return [
            ModuleSummary(
                id=str(m.id),
                course_id=str(m.course_id),
                slug=m.slug,
                title=m.title,
                description=m.description,
                sort_order=m.sort_order,
                is_published=bool(m.is_published),
            )
            for m in modules
        ]
