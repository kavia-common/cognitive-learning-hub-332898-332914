from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import text

from src.adapters.db import db_session
from src.core.auth import AuthUser, create_access_token, decode_access_token, hash_password, verify_password
from src.core.errors import conflict, unauthorized
from src.api.schemas import LoginRequest, MeResponse, SignupRequest, TokenResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
bearer = HTTPBearer(auto_error=False)


def _utcnow():
    return datetime.now(timezone.utc)


# PUBLIC_INTERFACE
def get_current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> AuthUser:
    """FastAPI dependency to get current authenticated user.

    Returns:
        AuthUser

    Raises:
        DomainError(UNAUTHORIZED) if missing/invalid token.
    """
    if creds is None or not creds.credentials:
        raise unauthorized("Missing bearer token")
    return decode_access_token(creds.credentials)


@router.post(
    "/signup",
    response_model=TokenResponse,
    summary="Create an account",
    description="Creates a user account and returns an access token.",
)
def signup(payload: SignupRequest) -> TokenResponse:
    with db_session() as session:
        # Password hash storage: table doesn't include password_hash by default in bootstrap.
        # We store credentials in a separate table to avoid altering the bootstrap schema.
        session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS user_credentials (user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, password_hash text NOT NULL);"
            )
        )

        existing = session.execute(text("SELECT id FROM users WHERE email = :email"), {"email": payload.email}).fetchone()
        if existing:
            raise conflict("EMAIL_TAKEN", "Email already registered.", details={"email": payload.email})

        user_id = uuid.uuid4()
        now = _utcnow()
        session.execute(
            text(
                "INSERT INTO users (id, email, full_name, is_admin, created_at, updated_at) VALUES (:id, :email, :full_name, false, :now, :now)"
            ),
            {"id": user_id, "email": payload.email, "full_name": payload.full_name, "now": now},
        )
        session.execute(
            text("INSERT INTO user_credentials (user_id, password_hash) VALUES (:uid, :ph)"),
            {"uid": user_id, "ph": hash_password(payload.password)},
        )
        session.commit()

        return TokenResponse(access_token=create_access_token(user_id=str(user_id), email=payload.email, is_admin=False))


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login",
    description="Authenticates a user and returns an access token.",
)
def login(payload: LoginRequest) -> TokenResponse:
    with db_session() as session:
        session.execute(
            text(
                "CREATE TABLE IF NOT EXISTS user_credentials (user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, password_hash text NOT NULL);"
            )
        )
        row = session.execute(
            text(
                "SELECT u.id, u.email, u.is_admin, c.password_hash FROM users u JOIN user_credentials c ON c.user_id=u.id WHERE u.email=:email"
            ),
            {"email": payload.email},
        ).fetchone()
        if not row:
            raise unauthorized("Invalid email or password")

        user_id, email, is_admin, password_hash = row
        if not verify_password(payload.password, password_hash):
            raise unauthorized("Invalid email or password")

        return TokenResponse(access_token=create_access_token(user_id=str(user_id), email=email, is_admin=bool(is_admin)))


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current user",
    description="Returns identity info for the bearer token.",
)
def me(user: AuthUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user_id=user.user_id, email=user.email, is_admin=user.is_admin)
