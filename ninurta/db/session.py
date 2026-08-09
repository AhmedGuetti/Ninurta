"""Database session management and initialization."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# ── Configuration ────────────────────────────────────────────────────────
# Default to a local SQLite database in the current working directory,
# but allow overriding via environment variable.
DB_URL = os.environ.get("NINURTA_DB_URL", "sqlite:///ninurta.db")

# ── Engine & Session ─────────────────────────────────────────────────────
engine = create_engine(
    DB_URL,
    echo=False,  # Set to True to log all SQL queries (for debugging)
    connect_args={"check_same_thread": False} if "sqlite" in DB_URL else {},
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()


def get_db() -> sessionmaker:
    """Yield a database session (useful for dependency injection if needed)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables defined in models.py, then run lightweight migrations."""
    # Import models so Base understands what tables to create
    from ninurta.db import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    _migrate()


def _migrate() -> None:
    """Add columns introduced after the table was first created (SQLite only)."""
    if "sqlite" not in DB_URL:
        return
    from sqlalchemy import inspect, text  # noqa: PLC0415

    inspector = inspect(engine)
    if "resumes" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("resumes")}
    if "parsed_json" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE resumes ADD COLUMN parsed_json TEXT"))
