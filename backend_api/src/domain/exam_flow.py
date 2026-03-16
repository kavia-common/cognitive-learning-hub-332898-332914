from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.errors import DomainError, conflict, not_found
from src.domain.models import Exam, ExamAttempt, ExamQuestion, ExamResponse, Question, QuestionChoice, ModuleProgress

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExamStartResult:
    attempt_id: str
    module_id: str
    started_at: datetime
    expires_at: datetime
    duration_seconds: int
    status: str


@dataclass(frozen=True)
class ExamQuestionsResult:
    module_id: str
    attempt_id: str
    questions: list[dict]


@dataclass(frozen=True)
class ExamSubmitResult:
    attempt_id: str
    status: str
    score_percent: float
    passed: bool
    total_questions: int
    correct_count: int
    correct_choice_ids_by_question_id: dict[str, list[str]]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _require_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except Exception as e:
        raise DomainError(code="VALIDATION_ERROR", message=f"Invalid {field}", http_status=422) from e


def _load_exam_by_module(session: Session, module_id: uuid.UUID) -> Exam:
    exam = session.execute(select(Exam).where(Exam.module_id == module_id)).scalar_one_or_none()
    if not exam:
        raise not_found("exam_for_module", str(module_id))
    return exam


def _compute_correct_map(session: Session, question_ids: list[uuid.UUID]) -> dict[str, list[str]]:
    if not question_ids:
        return {}
    rows = session.execute(
        select(QuestionChoice.question_id, QuestionChoice.id)
        .where(QuestionChoice.question_id.in_(question_ids))
        .where(QuestionChoice.is_correct.is_(True))
    ).all()
    out: dict[str, list[str]] = {}
    for qid, cid in rows:
        out.setdefault(str(qid), []).append(str(cid))
    return out


def _is_multi_select(session: Session, question_id: uuid.UUID) -> bool:
    # If a question has >1 correct choices, treat as multi-select.
    correct_count = session.execute(
        select(QuestionChoice).where(QuestionChoice.question_id == question_id).where(QuestionChoice.is_correct.is_(True))
    ).scalars().all()
    return len(correct_count) > 1


# PUBLIC_INTERFACE
def start_exam_attempt_flow(*, session: Session, user_id: str, module_id: str) -> ExamStartResult:
    """Start an exam attempt (server authoritative) enforcing single attempt per exam/user.

    Contract:
    - Inputs: user_id (uuid string), module_id (uuid string)
    - Output: ExamStartResult containing server started_at and expires_at
    - Errors:
      - NOT_FOUND if module has no exam
      - EXAM_ATTEMPT_ALREADY_EXISTS (409) if user already started/submitted/expired attempt (single attempt rule)
    - Side effects:
      - Creates exam_attempts row. Also upserts module_progress.started_at/last_activity_at.
    """
    module_uuid = _require_uuid(module_id, "module_id")
    user_uuid = _require_uuid(user_id, "user_id")

    logger.info("ExamAttemptFlow.start: user_id=%s module_id=%s", user_id, module_id)

    exam = _load_exam_by_module(session, module_uuid)
    now = _utcnow()
    expires_at = now  # will be overwritten by DB trigger if inserted w/ NULL, but we set explicitly.

    attempt = ExamAttempt(
        id=uuid.uuid4(),
        exam_id=exam.id,
        user_id=user_uuid,
        started_at=now,
        expires_at=now,  # updated below
        status="in_progress",
        total_questions=0,
        correct_count=0,
        score_percent=0.0,
        passed=False,
        created_at=now,
        updated_at=now,
    )
    # Compute expires_at in application layer to make response deterministic.
    expires_at = now.replace() + (datetime.fromtimestamp(now.timestamp() + exam.duration_seconds, tz=timezone.utc) - now)
    attempt.expires_at = expires_at

    try:
        session.add(attempt)

        # Ensure progress row exists
        progress = session.execute(
            select(ModuleProgress).where(ModuleProgress.user_id == user_uuid).where(ModuleProgress.module_id == module_uuid)
        ).scalar_one_or_none()
        if not progress:
            progress = ModuleProgress(
                id=uuid.uuid4(),
                user_id=user_uuid,
                module_id=module_uuid,
                started_at=now,
                completed_at=None,
                last_activity_at=now,
                exam_attempt_id=None,
                exam_passed=False,
                created_at=now,
                updated_at=now,
            )
            session.add(progress)
        else:
            if progress.started_at is None:
                progress.started_at = now
            progress.last_activity_at = now

        session.commit()
    except IntegrityError as e:
        session.rollback()
        raise conflict(
            "EXAM_ATTEMPT_ALREADY_EXISTS",
            "This exam only allows 1 attempt. An attempt already exists for this user.",
            details={"moduleId": module_id},
        ) from e

    return ExamStartResult(
        attempt_id=str(attempt.id),
        module_id=module_id,
        started_at=attempt.started_at,
        expires_at=attempt.expires_at,
        duration_seconds=exam.duration_seconds,
        status=attempt.status,
    )


# PUBLIC_INTERFACE
def get_exam_questions_flow(*, session: Session, user_id: str, module_id: str) -> ExamQuestionsResult:
    """Fetch exam questions for a module.

    Contract:
    - Requires an existing in_progress attempt for the user+module (single attempt model).
    - Questions are delivered without correctness flags.
    - Errors:
      - EXAM_ATTEMPT_REQUIRED if attempt not started
      - EXAM_ATTEMPT_NOT_IN_PROGRESS if already submitted/expired
    """
    module_uuid = _require_uuid(module_id, "module_id")
    user_uuid = _require_uuid(user_id, "user_id")

    exam = _load_exam_by_module(session, module_uuid)
    attempt = session.execute(
        select(ExamAttempt).where(ExamAttempt.exam_id == exam.id).where(ExamAttempt.user_id == user_uuid)
    ).scalar_one_or_none()
    if not attempt:
        raise DomainError(code="EXAM_ATTEMPT_REQUIRED", message="Start the exam before fetching questions.", http_status=409)
    if attempt.status != "in_progress":
        raise DomainError(code="EXAM_ATTEMPT_NOT_IN_PROGRESS", message="Attempt is not in progress.", http_status=409)

    # If exam_questions table is empty, fall back to module questions (active).
    eq_rows = session.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam.id).order_by(ExamQuestion.sort_order.asc())
    ).scalars().all()

    question_ids: list[uuid.UUID]
    if eq_rows:
        question_ids = [r.question_id for r in eq_rows]
    else:
        question_ids = [
            q.id
            for q in session.execute(
                select(Question).where(Question.module_id == module_uuid).where(Question.is_active.is_(True))
            )
            .scalars()
            .all()
        ]

    questions_out: list[dict] = []
    for qid in question_ids:
        q = session.execute(select(Question).where(Question.id == qid)).scalar_one()
        choices = session.execute(
            select(QuestionChoice).where(QuestionChoice.question_id == qid).order_by(QuestionChoice.sort_order.asc())
        ).scalars().all()
        questions_out.append(
            {
                "id": str(q.id),
                "prompt": q.prompt,
                "choices": [{"id": str(c.id), "text": c.choice_text} for c in choices],
                "multi_select": _is_multi_select(session, q.id),
            }
        )

    return ExamQuestionsResult(module_id=module_id, attempt_id=str(attempt.id), questions=questions_out)


# PUBLIC_INTERFACE
def submit_exam_attempt_flow(
    *,
    session: Session,
    user_id: str,
    module_id: str,
    attempt_id: str,
    answers_by_question_id: dict[str, list[str]],
) -> ExamSubmitResult:
    """Submit an exam attempt with atomic persistence of answers and attempt scoring.

    Contract:
    - Input:
      - attempt_id identifies the server-created attempt.
      - answers_by_question_id maps question_id -> selected_choice_ids
    - Server-authoritative checks:
      - attempt belongs to user
      - attempt is in_progress
      - now <= expires_at (else status becomes expired)
      - only 1 attempt exists by DB constraint
    - Atomicity:
      - Writes/updates exam_responses rows and marks attempt submitted/expired in a single DB transaction.
    - Deterministic errors:
      - ATTEMPT_NOT_FOUND (404)
      - ATTEMPT_FORBIDDEN (403) if attempt doesn't belong to user
      - ATTEMPT_NOT_IN_PROGRESS (409)
      - ATTEMPT_EXPIRED (409) if expired at submit time
    """
    module_uuid = _require_uuid(module_id, "module_id")
    user_uuid = _require_uuid(user_id, "user_id")
    attempt_uuid = _require_uuid(attempt_id, "attempt_id")

    logger.info("ExamAttemptFlow.submit: user_id=%s module_id=%s attempt_id=%s", user_id, module_id, attempt_id)

    exam = _load_exam_by_module(session, module_uuid)

    # Lock attempt row for update to ensure consistent scoring and state transition.
    attempt = session.execute(
        select(ExamAttempt).where(ExamAttempt.id == attempt_uuid).with_for_update()
    ).scalar_one_or_none()
    if not attempt:
        raise DomainError(code="ATTEMPT_NOT_FOUND", message="Attempt not found.", http_status=404)
    if attempt.user_id != user_uuid:
        raise DomainError(code="ATTEMPT_FORBIDDEN", message="Attempt does not belong to user.", http_status=403)
    if attempt.exam_id != exam.id:
        raise DomainError(code="ATTEMPT_MISMATCH", message="Attempt does not match module exam.", http_status=409)
    if attempt.status != "in_progress":
        raise DomainError(code="ATTEMPT_NOT_IN_PROGRESS", message="Attempt is not in progress.", http_status=409)

    now = _utcnow()
    if now > attempt.expires_at:
        attempt.status = "expired"
        attempt.submitted_at = attempt.submitted_at or now
        session.add(attempt)
        session.commit()
        raise DomainError(code="ATTEMPT_EXPIRED", message="Time expired. Attempt cannot be submitted.", http_status=409)

    # Determine question set for scoring (exam_questions preferred, else module active questions).
    eq_rows = session.execute(select(ExamQuestion).where(ExamQuestion.exam_id == exam.id)).scalars().all()
    if eq_rows:
        question_ids = [r.question_id for r in eq_rows]
    else:
        question_ids = [
            q.id
            for q in session.execute(
                select(Question).where(Question.module_id == module_uuid).where(Question.is_active.is_(True))
            )
            .scalars()
            .all()
        ]

    correct_map = _compute_correct_map(session, question_ids)

    # Upsert responses
    for qid in question_ids:
        qid_str = str(qid)
        selected_ids = answers_by_question_id.get(qid_str, [])
        # Single-select: if multiple sent, keep deterministic by taking first.
        if not _is_multi_select(session, qid) and len(selected_ids) > 1:
            selected_ids = selected_ids[:1]

        # Determine correctness:
        correct_ids = set(correct_map.get(qid_str, []))
        selected_set = set(selected_ids)
        is_correct = selected_set == correct_ids and len(correct_ids) > 0

        # For now, persist one selected choice in selected_choice_id (schema supports single),
        # but we still compute multi-select correctness and return correct map to client.
        selected_choice_uuid = _require_uuid(selected_ids[0], "selected_choice_id") if selected_ids else None

        existing = session.execute(
            select(ExamResponse).where(ExamResponse.attempt_id == attempt_uuid).where(ExamResponse.question_id == qid)
        ).scalar_one_or_none()
        if existing:
            existing.selected_choice_id = selected_choice_uuid
            existing.is_correct = is_correct
            existing.answered_at = now
            session.add(existing)
        else:
            session.add(
                ExamResponse(
                    id=uuid.uuid4(),
                    attempt_id=attempt_uuid,
                    question_id=qid,
                    selected_choice_id=selected_choice_uuid,
                    free_text_response=None,
                    is_correct=is_correct,
                    answered_at=now,
                )
            )

    total_questions = len(question_ids)
    correct_count = session.execute(
        select(ExamResponse).where(ExamResponse.attempt_id == attempt_uuid).where(ExamResponse.is_correct.is_(True))
    ).scalars().all()
    correct_num = len(correct_count)
    score_percent = 0.0 if total_questions == 0 else round((correct_num / total_questions) * 100.0, 2)
    passed = score_percent >= float(exam.pass_percent)

    attempt.total_questions = total_questions
    attempt.correct_count = correct_num
    attempt.score_percent = score_percent
    attempt.passed = passed
    attempt.submitted_at = now
    attempt.status = "submitted"
    session.add(attempt)

    # Update progress
    progress = session.execute(
        select(ModuleProgress).where(ModuleProgress.user_id == user_uuid).where(ModuleProgress.module_id == module_uuid)
    ).scalar_one_or_none()
    if not progress:
        progress = ModuleProgress(
            id=uuid.uuid4(),
            user_id=user_uuid,
            module_id=module_uuid,
            started_at=now,
            completed_at=None,
            last_activity_at=now,
            exam_attempt_id=attempt_uuid,
            exam_passed=passed,
            created_at=now,
            updated_at=now,
        )
        session.add(progress)
    else:
        progress.last_activity_at = now
        progress.exam_attempt_id = attempt_uuid
        progress.exam_passed = passed
        if passed and progress.completed_at is None:
            progress.completed_at = now
        session.add(progress)

    session.commit()

    return ExamSubmitResult(
        attempt_id=attempt_id,
        status=attempt.status,
        score_percent=float(score_percent),
        passed=bool(passed),
        total_questions=total_questions,
        correct_count=correct_num,
        correct_choice_ids_by_question_id=correct_map,
    )
