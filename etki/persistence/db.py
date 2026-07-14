"""SQLAlchemy engine/session. The backend is selected via Settings.db_url
(sqlite:///... or postgresql+psycopg://...). The core never knows the concrete DB.
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from etki.config import Settings


class Base(DeclarativeBase):
    pass


def make_engine(db_url: str | None = None) -> Engine:
    url = db_url or Settings().db_url
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False}, future=True)
    # Postgres etc.: auto-recycle stale connections (so the first query doesn't blow up
    # after a DB restart / idle timeout) + periodically recycle connections.
    return create_engine(url, pool_pre_ping=True, pool_recycle=1800, future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_schema(engine: Engine) -> None:
    from etki.persistence import models  # noqa: F401 — registers the tables

    Base.metadata.create_all(engine)


def build_repository(db_url: str | None = None):  # type: ignore[no-untyped-def]
    """Builds the schema + SqlCaseFileRepository from Settings.db_url (used by the api)."""
    from etki.persistence.repository import SqlCaseFileRepository

    engine = make_engine(db_url)
    init_schema(engine)
    return SqlCaseFileRepository(make_session_factory(engine))
