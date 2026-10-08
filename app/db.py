from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    # MVP: create tables on startup. Swap for Alembic migrations before production.
    from app import models  # noqa: F401  (register models on Base.metadata)

    # Advisory lock so the api and N workers starting together don't race on CREATE TYPE/TABLE.
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(424242)"))
        Base.metadata.create_all(conn)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
