import os
from pathlib import Path

import platformdirs
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, text

# Ensure Node is imported so it registers on SQLModel.metadata
from pathtree.models.node import Node  # noqa: F401


def get_db_path() -> Path:
    """Get platform-compliant application data path for the database.

    Supports override via PATHTREE_DB_PATH environment variable.
    """
    env_path = os.getenv("PATHTREE_DB_PATH")
    if env_path:
        return Path(env_path)
    data_dir = Path(platformdirs.user_data_dir("pathtree", appauthor=False))
    return data_dir / "pathtree.db"


def set_sqlite_pragma(dbapi_connection, connection_record) -> None:
    """Apply optimized SQLite pragmas (WAL mode, foreign keys)."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA foreign_keys=ON;")
    cursor.close()


def create_db_engine(db_path: Path) -> Engine:
    """Create a new SQLModel engine for the SQLite database."""
    if str(db_path) != ":memory:" and db_path.parent:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    event.listen(engine, "connect", set_sqlite_pragma)
    return engine


def init_db(engine: Engine) -> None:
    """Query user_version, generate tables if needed, and update user_version to 1."""
    with Session(engine) as session:
        connection = session.connection()

        # Check if 'nodes' table exists
        cursor = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes';")
        )
        table_exists = cursor.first() is not None

        version = connection.execute(text("PRAGMA user_version;")).scalar() or 0

        if not table_exists:
            # Create all tables defined in SQLModel metadata
            SQLModel.metadata.create_all(engine)
            # Set user_version to 1
            connection.execute(text("PRAGMA user_version = 1;"))
            session.commit()
        elif version == 0:
            # Table exists but version is 0, update it to 1
            connection.execute(text("PRAGMA user_version = 1;"))
            session.commit()


_engine: Engine | None = None


def get_engine() -> Engine:
    """Get or create the global database engine."""
    global _engine
    if _engine is None:
        db_path = get_db_path()
        _engine = create_db_engine(db_path)
        init_db(_engine)
    return _engine


def get_session() -> Session:
    """Create and return a new SQLModel Session."""
    return Session(get_engine())
