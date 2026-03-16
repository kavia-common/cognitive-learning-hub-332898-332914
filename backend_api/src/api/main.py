from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.core.config import get_settings
from src.core.errors import DomainError
from src.api.routes import auth_router, exams_router, modules_router, progress_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

openapi_tags = [
    {"name": "health", "description": "Health and diagnostics"},
    {"name": "auth", "description": "Authentication (signup/login/me)"},
    {"name": "modules", "description": "Course content: module listing and retrieval"},
    {"name": "exam", "description": "Timed exam attempt flow (1 attempt, 20 minutes, 80% pass)"},
    {"name": "progress", "description": "Learner progress tracking"},
]

app = FastAPI(
    title="Cognitive Learning Hub API",
    description=(
        "Backend API for modules and timed exam attempts.\n\n"
        "Exam rules (server authoritative):\n"
        "- Single attempt per user per module exam\n"
        "- Duration: 20 minutes (configurable per exam.duration_seconds)\n"
        "- Pass threshold: 80% (configurable per exam.pass_percent)\n"
        "- Attempt + answers are persisted atomically"
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
    """Convert DomainError into a deterministic JSON error payload."""
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "details": exc.details},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Fallback error handler with stable shape (prevents HTML/traceback leaks)."""
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message": "Internal server error"})


@app.get(
    "/",
    tags=["health"],
    summary="Health check",
    description="Simple health endpoint for uptime checks.",
)
def health_check() -> dict[str, Any]:
    return {"message": "Healthy"}


@app.get(
    "/healthz",
    tags=["health"],
    summary="Health check (preview readiness)",
    description=(
        "Health endpoint used by the preview system readiness probe. "
        "Must return 200 when the service is up."
    ),
)
def healthz() -> dict[str, Any]:
    return {"status": "ok"}


@app.get(
    "/docs/exam",
    tags=["exam"],
    summary="Exam API usage notes",
    description="Explains how to use the server-authoritative exam attempt flow.",
)
def exam_docs() -> dict[str, Any]:
    return {
        "flow": [
            "POST /modules/{moduleId}/exam/attempts/start  (creates attempt, sets started_at/expires_at)",
            "GET  /modules/{moduleId}/exam/questions       (requires in_progress attempt)",
            "POST /modules/{moduleId}/exam/attempts/submit (atomic answers+score; validates expiry)",
        ],
        "rules": {"maxAttempts": 1, "durationSeconds": "from exams.duration_seconds (default 1200)", "passThresholdPct": "from exams.pass_percent (default 80.00)"},
        "errors": [
            {"code": "EXAM_ATTEMPT_ALREADY_EXISTS", "when": "start called after prior attempt exists"},
            {"code": "ATTEMPT_EXPIRED", "when": "submit after expires_at"},
        ],
    }


# Route registration
app.include_router(auth_router)
app.include_router(modules_router)
app.include_router(exams_router)
app.include_router(progress_router)
