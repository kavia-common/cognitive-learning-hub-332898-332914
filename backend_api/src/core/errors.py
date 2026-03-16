from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainError(Exception):
    """Typed domain error to ensure deterministic API responses."""

    code: str
    message: str
    http_status: int = 400
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


# PUBLIC_INTERFACE
def not_found(entity: str, entity_id: str) -> DomainError:
    """Create a standardized not-found error."""
    return DomainError(code="NOT_FOUND", message=f"{entity} '{entity_id}' not found", http_status=404)


# PUBLIC_INTERFACE
def conflict(code: str, message: str, details: dict[str, Any] | None = None) -> DomainError:
    """Create a standardized conflict error."""
    return DomainError(code=code, message=message, http_status=409, details=details)


# PUBLIC_INTERFACE
def forbidden(code: str, message: str) -> DomainError:
    """Create a standardized forbidden error."""
    return DomainError(code=code, message=message, http_status=403)


# PUBLIC_INTERFACE
def unauthorized(message: str = "Unauthorized") -> DomainError:
    """Create a standardized unauthorized error."""
    return DomainError(code="UNAUTHORIZED", message=message, http_status=401)
