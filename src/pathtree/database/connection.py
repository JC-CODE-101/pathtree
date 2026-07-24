import os
from pathlib import Path

import platformdirs
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, text

# Ensure models are imported so they register on SQLModel.metadata
from pathtree.models.node import Node  # noqa: F401
from pathtree.models.pin import Pin  # noqa: F401


class UnsupportedDatabaseVersionError(Exception):
    """Raised when the SQLite database has a newer unsupported version."""


class DatabaseMigrationError(Exception):
    """Raised when a database schema migration fails and is rolled back."""


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
    """Query user_version, generate tables if needed, and migrate to version 3.

    If the database reports user_version > 3, we refuse startup with
    UnsupportedDatabaseVersionError.
    Fresh database creates tables directly at version 3.
    An existing version 1 (or 0) database is migrated transactionally to
    version 2, then to 3.
    An existing version 2 database is migrated transactionally to version 3.
    Version 3 database no-ops cleanly.
    """
    with Session(engine) as session:
        connection = session.connection()

        # Read version before any database mutation or table checks
        version = connection.execute(text("PRAGMA user_version;")).scalar() or 0

        if version > 3:
            raise UnsupportedDatabaseVersionError(
                f"Database version {version} is newer than the supported version 3."
            )

        # Check if 'nodes' table exists after version check
        cursor = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes';")
        )
        table_exists = cursor.first() is not None

        if not table_exists:
            # Create all tables defined in SQLModel metadata
            SQLModel.metadata.create_all(engine)
            # Set user_version to 3
            connection.execute(text("PRAGMA user_version = 3;"))
            session.commit()
            return

        # Sequential migrations for existing databases
        if version in (0, 1):
            # Use raw DBAPI connection to handle transactional DDL in SQLite correctly
            # and prevent python sqlite3 auto-committing on ALTER TABLE statements.
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")

                # 1. Add new columns
                cursor.execute(
                    "ALTER TABLE nodes ADD COLUMN "
                    "node_kind VARCHAR NOT NULL DEFAULT 'resource';"
                )
                cursor.execute(
                    "ALTER TABLE nodes ADD COLUMN resource_type VARCHAR DEFAULT NULL;"
                )
                cursor.execute(
                    "ALTER TABLE nodes ADD COLUMN "
                    "is_favorite BOOLEAN NOT NULL DEFAULT 0;"
                )
                cursor.execute(
                    "ALTER TABLE nodes ADD COLUMN "
                    "is_temporary BOOLEAN NOT NULL DEFAULT 0;"
                )

                # 2. Convert legacy data
                cursor.execute(
                    "UPDATE nodes SET node_kind = 'workspace', resource_type = NULL "
                    "WHERE node_type = 'Workspace';"
                )
                cursor.execute(
                    "UPDATE nodes SET node_kind = 'folder', resource_type = NULL "
                    "WHERE node_type = 'Folder' AND (path IS NULL OR path = '');"
                )
                cursor.execute(
                    "UPDATE nodes SET node_kind = 'resource', "
                    "resource_type = 'directory' WHERE node_type = 'Folder' "
                    "AND path IS NOT NULL AND path != '';"
                )

                # 3. Create indexes idempotently
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_nodes_node_kind ON nodes (node_kind);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_nodes_resource_type ON nodes (resource_type);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_nodes_is_favorite ON nodes (is_favorite);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_nodes_is_temporary ON nodes (is_temporary);"
                )

                # 4. Set version to 2
                cursor.execute("PRAGMA user_version = 2;")
                dbapi_conn.commit()
                cursor.close()
                version = 2
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Migration from version {version} to 2 failed. "
                    "All changes rolled back."
                ) from e

        if version == 2:
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")

                # Create pins table with foreign key ON DELETE CASCADE
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS pins (
                        id VARCHAR NOT NULL,
                        node_id VARCHAR NOT NULL,
                        position INTEGER NOT NULL,
                        custom_label VARCHAR,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(node_id) REFERENCES nodes (id) ON DELETE CASCADE
                    );
                """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_pins_node_id ON pins (node_id);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_pins_position ON pins (position);"
                )

                cursor.execute("PRAGMA user_version = 3;")
                dbapi_conn.commit()
                cursor.close()
                version = 3
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Migration from version {version} to 3 failed. "
                    "All changes rolled back."
                ) from e


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
