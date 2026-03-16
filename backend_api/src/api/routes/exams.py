from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.adapters.db import db_session
from src.api.routes.auth import AuthUser, get_current_user
from src.api.schemas import (
    ExamConfigResponse,
    ExamStartResponse,
    ExamSubmitRequest,
    ExamSubmitResponse,
    Question,
)
from src.domain.exam_flow import get_exam_questions_flow, start_exam_attempt_flow, submit_exam_attempt_flow
from src.domain.models import Exam, ExamQuestion, Question as DbQuestion

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/modules/{module_id}/exam", tags=["exam"])


@router.get(
    "/config",
    response_model=ExamConfigResponse,
    summary="Get module exam config",
    description="Returns duration, maxAttempts (1), passThresholdPct (>=80), and questionCount.",
)
def get_exam_config(module_id: str, user: AuthUser = Depends(get_current_user)) -> ExamConfigResponse:
    with db_session() as session:
        exam = session.execute(select(Exam).where(Exam.module_id == module_id)).scalar_one_or_none()
        if not exam:
            # If exam row not present, expose default configuration (still consistent with product rules).
            return ExamConfigResponse(
                module_id=module_id,
                duration_seconds=20 * 60,
                max_attempts=1,
                pass_threshold_pct=80.0,
                question_count=0,
            )

        # Count questions via exam_questions if present else module questions
        eq_count = session.execute(select(ExamQuestion).where(ExamQuestion.exam_id == exam.id)).scalars().all()
        if eq_count:
            count = len(eq_count)
        else:
            count = (
                session.execute(
                    select(DbQuestion).where(DbQuestion.module_id == exam.module_id).where(DbQuestion.is_active.is_(True))
                )
                .scalars()
                .all()
            )
            count = len(count)

        return ExamConfigResponse(
            module_id=module_id,
            duration_seconds=int(exam.duration_seconds),
            max_attempts=1,
            pass_threshold_pct=float(exam.pass_percent),
            question_count=int(count),
        )


@router.post(
    "/attempts/start",
    response_model=ExamStartResponse,
    summary="Start exam attempt",
    description="Server-authoritative attempt creation enforcing single attempt per user and 20-minute expiration.",
)
def start_attempt(module_id: str, user: AuthUser = Depends(get_current_user)) -> ExamStartResponse:
    with db_session() as session:
        result = start_exam_attempt_flow(session=session, user_id=user.user_id, module_id=module_id)
        return ExamStartResponse(
            attempt_id=result.attempt_id,
            module_id=result.module_id,
            started_at=result.started_at,
            expires_at=result.expires_at,
            duration_seconds=result.duration_seconds,
            status=result.status,
        )


@router.get(
    "/questions",
    response_model=list[Question],
    summary="Get exam questions",
    description="Returns the exam questions for the active attempt (no answers).",
)
def get_questions(module_id: str, user: AuthUser = Depends(get_current_user)) -> list[Question]:
    with db_session() as session:
        result = get_exam_questions_flow(session=session, user_id=user.user_id, module_id=module_id)
        return [Question(**q) for q in result.questions]


@router.post(
    "/attempts/submit",
    response_model=ExamSubmitResponse,
    summary="Submit exam attempt",
    description="Validates time window, persists answers atomically, computes score, and returns pass/fail (>=80%).",
)
def submit_attempt(module_id: str, payload: ExamSubmitRequest, user: AuthUser = Depends(get_current_user)) -> ExamSubmitResponse:
    with db_session() as session:
        result = submit_exam_attempt_flow(
            session=session,
            user_id=user.user_id,
            module_id=module_id,
            attempt_id=payload.attempt_id,
            answers_by_question_id=payload.answers_by_question_id,
        )
        return ExamSubmitResponse(
            attempt_id=result.attempt_id,
            status=result.status,
            score_percent=result.score_percent,
            passed=result.passed,
            total_questions=result.total_questions,
            correct_count=result.correct_count,
            correct_choice_ids_by_question_id=result.correct_choice_ids_by_question_id,
        )
