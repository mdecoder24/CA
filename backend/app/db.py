"""Database engine and session helpers.

All bank data lives in a single SQLite file under the data directory.
Set FINTRACK_DATA_DIR to override (tests use a temporary directory).
"""

import os
from pathlib import Path

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def data_dir() -> Path:
    d = Path(os.environ.get("FINTRACK_DATA_DIR", REPO_ROOT / "data"))
    (d / "uploads").mkdir(parents=True, exist_ok=True)
    (d / "exports").mkdir(parents=True, exist_ok=True)
    return d


_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = f"sqlite:///{data_dir() / 'fintrack.db'}"
        _engine = create_engine(url, connect_args={"check_same_thread": False})

        @event.listens_for(_engine, "connect")
        def _fk_on(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.execute("PRAGMA journal_mode=WAL")
            cur.close()

    return _engine


def reset_engine() -> None:
    """Drop the cached engine (used by tests after changing FINTRACK_DATA_DIR)."""
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)
    from .seed import seed

    SQLModel.metadata.create_all(get_engine())
    with Session(get_engine()) as s:
        seed(s)


def get_session():
    with Session(get_engine()) as s:
        yield s
