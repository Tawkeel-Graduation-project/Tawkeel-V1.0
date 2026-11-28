"""Database engine and session dependency."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    """Create and cache the SQLAlchemy engine lazily from application settings."""
    return create_app_engine(get_settings().sqlalchemy_database_url)


def create_app_engine(url: str) -> Engine:
    """An engine whose every connection uses the UTC session time zone.

    Naive timestamp columns are filled by ``now()``, which writes the session's
    local time; pinning UTC keeps them UTC, as the API assumes (SCRUM-359).
    """
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Create and cache the session factory bound to the lazy engine."""
    return sessionmaker(
        bind=get_engine(),
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session.

    Rolls back on error and always closes the session.
    """
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
