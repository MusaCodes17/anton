"""
Database configuration and session management
"""
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./shoe_deals.db")

# Create engine
# For SQLite, we need to enable check_same_thread=False
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


# Dependency to get database session
def get_db():
    """
    Dependency function to provide database session to routes
    Usage: db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations() -> None:
    """
    Bring the database up to Alembic head — the *sole* schema authority (R2.2).

    Called at app startup (see main.py lifespan). Replaces the former
    `init_db()`/`Base.metadata.create_all` boot path: `create_all` cannot ALTER
    existing tables, so it silently masked schema drift on a live DB (CLAUDE.md
    §9's "dual schema authority" trap; design_decisions A6). Running the
    migrations instead means a fresh DB is built from the baseline forward and an
    existing one is upgraded in place — one path, always correct.

    Idempotent: a no-op when the DB is already at head. `create_all` now lives
    only in the test fixtures (tests/conftest.py, tests/test_auth.py), which
    build a throwaway in-memory/temp schema and never touch Alembic.
    """
    from alembic import command
    from alembic.config import Config

    backend_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(backend_root / "alembic.ini"))
    # env.py reads DATABASE_URL from the environment itself; no override needed.
    command.upgrade(alembic_cfg, "head")
