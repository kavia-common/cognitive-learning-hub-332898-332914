from __future__ import annotations

import time
from dataclasses import dataclass

import jwt
from passlib.context import CryptContext

from src.core.config import get_settings
from src.core.errors import DomainError, unauthorized

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@dataclass(frozen=True)
class AuthUser:
    """Authenticated user identity extracted from JWT."""
    user_id: str
    email: str
    is_admin: bool


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a password."""
    return _pwd_context.hash(password)


# PUBLIC_INTERFACE
def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    return _pwd_context.verify(password, password_hash)


# PUBLIC_INTERFACE
def create_access_token(*, user_id: str, email: str, is_admin: bool) -> str:
    """Create a signed JWT access token."""
    s = get_settings()
    if not s.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set")
    now = int(time.time())
    payload = {
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "iat": now,
        "exp": now + s.access_token_ttl_seconds,
        "sub": user_id,
        "email": email,
        "is_admin": is_admin,
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


# PUBLIC_INTERFACE
def decode_access_token(token: str) -> AuthUser:
    """Decode and validate a JWT access token.

    Raises:
        DomainError(UNAUTHORIZED) if invalid/expired.
    """
    s = get_settings()
    if not s.jwt_secret:
        raise RuntimeError("JWT_SECRET is not set")
    try:
        payload = jwt.decode(
            token,
            s.jwt_secret,
            algorithms=["HS256"],
            audience=s.jwt_audience,
            issuer=s.jwt_issuer,
        )
        return AuthUser(
            user_id=str(payload.get("sub")),
            email=str(payload.get("email")),
            is_admin=bool(payload.get("is_admin", False)),
        )
    except Exception as e:
        raise unauthorized("Invalid or expired token") from e


# PUBLIC_INTERFACE
def require(condition: bool, err: DomainError) -> None:
    """Raise the provided DomainError if condition is false."""
    if not condition:
        raise err
