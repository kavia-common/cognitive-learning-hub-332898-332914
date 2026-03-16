from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-friendly error message")
    details: dict[str, Any] | None = Field(default=None, description="Optional structured error details")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")


class SignupRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., min_length=8, description="User password (min 8 chars)")
    full_name: str | None = Field(default=None, description="Optional display name")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email")
    password: str = Field(..., description="User password")


class MeResponse(BaseModel):
    user_id: str = Field(..., description="User id (uuid)")
    email: str = Field(..., description="User email")
    is_admin: bool = Field(..., description="Whether the user is an admin")


class ModuleSummary(BaseModel):
    id: str = Field(..., description="Module id (uuid)")
    course_id: str = Field(..., description="Course id (uuid)")
    slug: str = Field(..., description="Module slug")
    title: str = Field(..., description="Module title")
    description: str | None = Field(default=None, description="Module description")
    sort_order: int = Field(..., description="Sort order")
    is_published: bool = Field(..., description="Published flag")


class ExamConfigResponse(BaseModel):
    module_id: str = Field(..., description="Module id (uuid)")
    duration_seconds: int = Field(..., description="Exam duration in seconds")
    max_attempts: int = Field(default=1, description="Max attempts allowed (always 1 for this product)")
    pass_threshold_pct: float = Field(..., description="Pass threshold percent (>=80 passes)")
    question_count: int = Field(..., description="Number of questions delivered")


class Choice(BaseModel):
    id: str = Field(..., description="Choice id (uuid)")
    text: str = Field(..., description="Choice text")


class Question(BaseModel):
    id: str = Field(..., description="Question id (uuid)")
    prompt: str = Field(..., description="Question prompt")
    choices: list[Choice] = Field(default_factory=list, description="Multiple choice options")
    multi_select: bool = Field(default=False, description="Whether multiple selections are allowed")


class ExamStartResponse(BaseModel):
    attempt_id: str = Field(..., description="Server-created attempt id (uuid)")
    module_id: str = Field(..., description="Module id (uuid)")
    started_at: datetime = Field(..., description="Server-authoritative start time")
    expires_at: datetime = Field(..., description="Server-authoritative expiration time")
    duration_seconds: int = Field(..., description="Duration in seconds")
    status: str = Field(..., description="Attempt status: in_progress|submitted|expired")


class ExamSubmitRequest(BaseModel):
    attempt_id: str = Field(..., description="Attempt id (uuid)")
    answers_by_question_id: dict[str, list[str]] = Field(
        ..., description="Map: question_id -> selected_choice_id(s). For single-select, send list length 1."
    )


class ExamSubmitResponse(BaseModel):
    attempt_id: str = Field(..., description="Attempt id (uuid)")
    status: str = Field(..., description="submitted|expired")
    score_percent: float = Field(..., description="Score percentage 0-100")
    passed: bool = Field(..., description="Whether score >= pass threshold")
    total_questions: int = Field(..., description="Total exam questions")
    correct_count: int = Field(..., description="Count correct")
    correct_choice_ids_by_question_id: dict[str, list[str]] = Field(
        ..., description="For each question: list of correct choice ids"
    )
