import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./equipe.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_column(table: str, column: str, ddl_type: str) -> None:
    """Add a column to an already-existing table if it's missing.

    Base.metadata.create_all() only creates tables that don't exist yet — it never
    ALTERs an existing one, so a schema change like adding a column needs this to
    not crash every already-deployed database on first write. No real migration
    tool (e.g. Alembic) for a single SQLite file feels like overkill here; this
    covers the actual need.
    """
    with engine.connect() as conn:
        existing = {row[1] for row in conn.exec_driver_sql(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.exec_driver_sql(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}")
            conn.commit()
