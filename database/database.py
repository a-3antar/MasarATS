
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config.settings import get_settings
from core.logging import get_logger
from database.guards import register_session_guards  # noqa: E402

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass

def _build_engine():
    settings = get_settings()
    connect_args = (
        {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {}
    )
    engine = create_engine(settings.database_url, connect_args=connect_args, echo=False)

    if settings.database_url.startswith("sqlite"):
        from sqlalchemy import event

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, _):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
            cursor.close()

    return engine

engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

register_session_guards(SessionLocal)

def _add_missing_columns() -> None:
    inspector = inspect(engine)
    with engine.begin() as connection:
        for table in Base.metadata.sorted_tables:
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                column_type = column.type.compile(dialect=engine.dialect)
                connection.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {column_type}"))
                logger.info("Added missing column %s.%s", table.name, column.name)

def init_db() -> None:
    from models import (
        application, application_stage_history, candidate, department, interview, interview_answer,
        job, job_question, offer, position, user,
    )  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()

    from services.question_bank_service import migrate_legacy_bank
    with get_db_session() as session:
        migrate_legacy_bank(session)
    logger.info("Database initialized (tables ensured).")

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
