from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from src.core.config import get_settings


def _build_sqlalchemy_url() -> str:
    """Build a SQLAlchemy connection string from POSTGRES_* env vars.

    The database_service provides POSTGRES_URL typically like:
      postgresql://localhost:5000/myapp
    but without credentials. We inject credentials if present.

    Contract:
    - Returns a SQLAlchemy-compatible URL for psycopg3.
    - If POSTGRES_URL already includes credentials, we keep it.
    """
    s = get_settings()
    base = s.postgres_url.strip()

    if not base:
        # Keep error handling deterministic at API boundary
        raise RuntimeError("POSTGRES_URL is not set")

    # If URL already contains '@', assume credentials already included.
    if "@" in base:
        return base

    # Expected base: postgresql://host:port/db
    # Inject: postgresql://user:pass@host:port/db
    if base.startswith("postgresql://"):
        return base.replace("postgresql://", f"postgresql://{s.postgres_user}:{s.postgres_password}@", 1)

    return base


_ENGINE: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


# PUBLIC_INTERFACE
def get_engine() -> Engine:
    """Return a singleton SQLAlchemy Engine."""
    global _ENGINE, _SessionLocal
    if _ENGINE is None:
        url = _build_sqlalchemy_url()
        _ENGINE = create_engine(url, pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(bind=_ENGINE, autocommit=False, autoflush=False, future=True)
    return _ENGINE


# PUBLIC_INTERFACE
def get_sessionmaker() -> sessionmaker[Session]:
    """Return the singleton sessionmaker."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal


# PUBLIC_INTERFACE
@contextmanager
def db_session() -> Session:
    """Context manager that yields a Session and ensures rollback on error.

    Side effects:
    - Starts a DB transaction scope; commits only when caller calls commit().

    Note:
    - We intentionally do NOT auto-commit here, to make transaction boundaries explicit
      in flows and allow atomic attempt+answers persistence.
    """
    SessionLocal = get_sessionmaker()
    session = SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
