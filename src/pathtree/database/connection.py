import os
from pathlib import Path

import platformdirs
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine, text

from pathtree.models.launch_profile import LaunchProfile  # noqa: F401
from pathtree.models.multi_launcher import (  # noqa: F401
    MultiLauncher,
    MultiLauncherItem,
)

# Ensure models are imported so they register on SQLModel.metadata
from pathtree.models.node import Node  # noqa: F401
from pathtree.models.pin import Pin  # noqa: F401
from pathtree.models.workspace_view_settings import WorkspaceViewSettings  # noqa: F401


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
    """Query user_version, generate tables if needed, and migrate to version 8.

    If the database reports user_version > 8, we refuse startup with
    UnsupportedDatabaseVersionError.
    Fresh database creates tables directly at version 8.
    An existing version 1 (or 0) database is migrated transactionally to
    version 2, then to 3, to 4, to 5, to 6, to 7, and then to 8.
    An existing version 2 database is migrated to 3, 4, 5, 6, 7, and then to 8.
    An existing version 3 database is migrated to 4, 5, 6, 7, and then to 8.
    An existing version 4 database is migrated to 5, 6, 7, and then to 8.
    An existing version 5 database is migrated to 6, 7, and then to 8.
    An existing version 6 database is migrated to 7, and then to 8.
    An existing version 7 database is migrated to 8.
    Version 8 database no-ops cleanly.
    """
    with Session(engine) as session:
        connection = session.connection()

        # Read version before any database mutation or table checks
        version = connection.execute(text("PRAGMA user_version;")).scalar() or 0

        if version > 8:
            raise UnsupportedDatabaseVersionError(
                f"Database version {version} is newer than the supported version 8."
            )

        # Check if 'nodes' table exists after version check
        cursor = connection.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes';")
        )
        table_exists = cursor.first() is not None

        if not table_exists:
            # Create all tables defined in SQLModel metadata
            SQLModel.metadata.create_all(engine)
            # Set user_version to 8
            connection.execute(text("PRAGMA user_version = 8;"))
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

        if version == 3:
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")

                # Add system_role column to nodes table
                cursor.execute(
                    "ALTER TABLE nodes ADD COLUMN system_role VARCHAR DEFAULT NULL;"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_nodes_system_role ON nodes (system_role);"
                )

                # Create launch_profiles table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS launch_profiles (
                        id VARCHAR NOT NULL,
                        profile_node_id VARCHAR NOT NULL,
                        workspace_id VARCHAR NOT NULL,
                        target_node_id VARCHAR,
                        target_resource_type VARCHAR NOT NULL,
                        arguments TEXT NOT NULL,
                        working_directory_node_id VARCHAR,
                        terminal_mode VARCHAR NOT NULL,
                        status VARCHAR NOT NULL,
                        previous_target_name VARCHAR,
                        previous_target_path VARCHAR,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(profile_node_id) REFERENCES nodes (id) ON DELETE CASCADE,
                        FOREIGN KEY(workspace_id) REFERENCES nodes (id) ON DELETE CASCADE,
                        FOREIGN KEY(target_node_id) REFERENCES nodes (id) ON DELETE SET NULL,
                        FOREIGN KEY(working_directory_node_id) REFERENCES nodes (id) ON DELETE SET NULL
                    );
                """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_launch_profiles_profile_node_id ON launch_profiles (profile_node_id);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_launch_profiles_workspace_id ON launch_profiles (workspace_id);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_launch_profiles_target_node_id ON launch_profiles (target_node_id);"
                )

                cursor.execute("PRAGMA user_version = 4;")
                dbapi_conn.commit()
                cursor.close()
                version = 4
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Migration from version {version} to 4 failed. "
                    "All changes rolled back."
                ) from e

        if version == 4:
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")

                # Create multi_launchers table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS multi_launchers (
                        id VARCHAR NOT NULL,
                        launcher_node_id VARCHAR NOT NULL,
                        workspace_id VARCHAR NOT NULL,
                        name VARCHAR NOT NULL,
                        description VARCHAR,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(launcher_node_id)
                            REFERENCES nodes (id) ON DELETE CASCADE,
                        FOREIGN KEY(workspace_id)
                            REFERENCES nodes (id) ON DELETE CASCADE
                    );
                """)

                # Create multi_launcher_items table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS multi_launcher_items (
                        id VARCHAR NOT NULL,
                        multi_launcher_id VARCHAR NOT NULL,
                        launch_profile_id VARCHAR NOT NULL,
                        position INTEGER NOT NULL,
                        enabled BOOLEAN NOT NULL,
                        delay_ms INTEGER NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(multi_launcher_id)
                            REFERENCES multi_launchers (id) ON DELETE CASCADE,
                        FOREIGN KEY(launch_profile_id)
                            REFERENCES launch_profiles (id) ON DELETE CASCADE
                    );
                """)

                # Create indexes
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_multi_launchers_launcher_node_id "
                    "ON multi_launchers (launcher_node_id);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_multi_launchers_workspace_id "
                    "ON multi_launchers (workspace_id);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_multi_launcher_items_multi_launcher_id "
                    "ON multi_launcher_items (multi_launcher_id);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS "
                    "ix_multi_launcher_items_launch_profile_id "
                    "ON multi_launcher_items (launch_profile_id);"
                )

                cursor.execute("PRAGMA user_version = 5;")
                dbapi_conn.commit()
                cursor.close()
                version = 5
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Migration from version {version} to 5 failed. "
                    "All changes rolled back."
                ) from e

        if version == 5:
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")

                # Create resource_references table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS resource_references (
                        id VARCHAR NOT NULL,
                        reference_node_id VARCHAR NOT NULL,
                        original_node_id VARCHAR,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(reference_node_id) REFERENCES nodes (id) ON DELETE CASCADE,
                        FOREIGN KEY(original_node_id) REFERENCES nodes (id) ON DELETE SET NULL
                    );
                """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_resource_references_reference_node_id ON resource_references (reference_node_id);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_resource_references_original_node_id ON resource_references (original_node_id);"
                )

                cursor.execute("PRAGMA user_version = 6;")
                dbapi_conn.commit()
                cursor.close()
                version = 6
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Migration from version {version} to 6 failed. "
                    "All changes rolled back."
                ) from e

        if version == 6:
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")

                # Create workspace_view_settings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS workspace_view_settings (
                        id VARCHAR NOT NULL,
                        workspace_id VARCHAR NOT NULL,
                        current_mode VARCHAR NOT NULL,
                        last_filter_mask INTEGER NOT NULL,
                        hide_empty_sections BOOLEAN NOT NULL,
                        show_system BOOLEAN NOT NULL,
                        show_custom BOOLEAN NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(workspace_id) REFERENCES nodes (id) ON DELETE CASCADE,
                        UNIQUE(workspace_id)
                    );
                """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_workspace_view_settings_workspace_id ON workspace_view_settings (workspace_id);"
                )

                cursor.execute("PRAGMA user_version = 7;")
                dbapi_conn.commit()
                cursor.close()
                version = 7
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Migration from version {version} to 7 failed. "
                    "All changes rolled back."
                ) from e

        if version == 7:
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")

                # Version 8: No direct schema changes required, user_version update only.
                cursor.execute("PRAGMA user_version = 8;")
                dbapi_conn.commit()
                cursor.close()
                version = 8
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Migration from version {version} to 8 failed. "
                    "All changes rolled back."
                ) from e

        # Final Verification Check: Ensure 'resource_references' table exists on startup
        cursor = connection.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='resource_references';"
            )
        )
        if cursor.first() is None:
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS resource_references (
                        id VARCHAR NOT NULL,
                        reference_node_id VARCHAR NOT NULL,
                        original_node_id VARCHAR,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(reference_node_id) REFERENCES nodes (id) ON DELETE CASCADE,
                        FOREIGN KEY(original_node_id) REFERENCES nodes (id) ON DELETE SET NULL
                    );
                """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_resource_references_reference_node_id ON resource_references (reference_node_id);"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_resource_references_original_node_id ON resource_references (original_node_id);"
                )
                cursor.execute("PRAGMA user_version = 8;")
                cursor.execute("PRAGMA user_version = 8;")
                dbapi_conn.commit()
                cursor.close()
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Startup verification and creation of resource_references failed: {e}"
                ) from e

        # Final Verification Check: Ensure 'workspace_view_settings' table exists on startup
        cursor = connection.execute(
            text(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_view_settings';"
            )
        )
        if cursor.first() is None:
            dbapi_conn = connection.connection.dbapi_connection
            try:
                cursor = dbapi_conn.cursor()
                cursor.execute("BEGIN TRANSACTION;")
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS workspace_view_settings (
                        id VARCHAR NOT NULL,
                        workspace_id VARCHAR NOT NULL,
                        current_mode VARCHAR NOT NULL,
                        last_filter_mask INTEGER NOT NULL,
                        hide_empty_sections BOOLEAN NOT NULL,
                        show_system BOOLEAN NOT NULL,
                        show_custom BOOLEAN NOT NULL,
                        created_at DATETIME NOT NULL,
                        updated_at DATETIME NOT NULL,
                        PRIMARY KEY (id),
                        FOREIGN KEY(workspace_id) REFERENCES nodes (id) ON DELETE CASCADE,
                        UNIQUE(workspace_id)
                    );
                """)
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS ix_workspace_view_settings_workspace_id ON workspace_view_settings (workspace_id);"
                )
                cursor.execute("PRAGMA user_version = 7;")
                dbapi_conn.commit()
                cursor.close()
            except Exception as e:
                try:
                    dbapi_conn.rollback()
                except Exception:
                    pass
                raise DatabaseMigrationError(
                    f"Startup verification and creation of workspace_view_settings failed: {e}"
                ) from e

        # Relocate legacy workspaces and their children deterministically
        migrate_existing_workspaces(connection)
        session.commit()


def migrate_existing_workspaces(connection) -> None:
    """Migrate all legacy workspaces and their children to the new System/Custom layout."""
    import uuid

    # 1. Fetch all nodes from nodes table
    cursor = connection.execute(
        text(
            "SELECT id, parent_id, name, node_kind, resource_type, system_role FROM nodes;"
        )
    )
    all_nodes = []
    for row in cursor.all():
        row_dict = dict(row._mapping)
        # Normalize IDs to hex without hyphens to match SQLModel storage format
        if row_dict["id"]:
            row_dict["id"] = row_dict["id"].replace("-", "")
        if row_dict["parent_id"]:
            row_dict["parent_id"] = row_dict["parent_id"].replace("-", "")
        all_nodes.append(row_dict)

    nodes_by_id = {n["id"]: n for n in all_nodes}

    workspaces = [n for n in all_nodes if n["node_kind"] == "workspace"]
    if not workspaces:
        return

    # Helper to find workspace ID for any node in the database
    def find_workspace_id(node_id: str) -> str | None:
        curr_id = node_id.replace("-", "")
        visited = set()
        while curr_id is not None:
            if curr_id in visited:
                break
            visited.add(curr_id)
            node = nodes_by_id.get(curr_id)
            if not node:
                break
            if node["node_kind"] == "workspace":
                return curr_id
            curr_id = node["parent_id"]
            if curr_id:
                curr_id = curr_id.replace("-", "")
        return None

    # Helper to create a node in SQL
    def db_create_node(
        name: str, node_kind: str, parent_id: str | None, system_role: str | None = None
    ) -> str:
        nid = uuid.uuid4().hex
        pid = parent_id.replace("-", "") if parent_id else None
        connection.execute(
            text(
                "INSERT INTO nodes (id, name, node_kind, parent_id, system_role, is_favorite, is_temporary, sort_order, created_at, updated_at, node_type) "
                "VALUES (:id, :name, :node_kind, :parent_id, :system_role, 0, 0, 0, datetime('now'), datetime('now'), 'Folder');"
            ),
            {
                "id": nid,
                "name": name,
                "node_kind": node_kind,
                "parent_id": pid,
                "system_role": system_role,
            },
        )
        new_node = {
            "id": nid,
            "parent_id": pid,
            "name": name,
            "node_kind": node_kind,
            "resource_type": None,
            "system_role": system_role,
        }
        nodes_by_id[nid] = new_node
        return nid

    # For each workspace, ensure System and Custom groups exist, and System has its 7 subsections
    workspace_layouts = {}
    for ws in workspaces:
        ws_id = ws["id"]
        sys_group_id = None
        custom_group_id = None
        for n in all_nodes:
            if n["parent_id"] == ws_id and n["node_kind"] == "system_group":
                if n["system_role"] == "system":
                    sys_group_id = n["id"]
                elif n["system_role"] == "custom":
                    custom_group_id = n["id"]

        if not sys_group_id:
            sys_group_id = db_create_node("System", "system_group", ws_id, "system")
        if not custom_group_id:
            custom_group_id = db_create_node("Custom", "system_group", ws_id, "custom")

        # Ensure System has the 7 subsections
        subsections = {
            "directories": "Directories",
            "files": "Files",
            "scripts": "Scripts",
            "executables": "Executables",
            "urls": "URLs",
            "launch_profiles": "Launch Profiles",
            "multi_launchers": "Multi Launchers",
        }
        subsection_ids = {}
        for role, name in subsections.items():
            sub_id = None
            for n in all_nodes:
                if (
                    n["parent_id"] == sys_group_id
                    and n["node_kind"] == "system_group"
                    and n["system_role"] == role
                ):
                    sub_id = n["id"]
            if not sub_id:
                sub_id = db_create_node(name, "system_group", sys_group_id, role)
            subsection_ids[role] = sub_id

        workspace_layouts[ws_id] = {
            "system": sys_group_id,
            "custom": custom_group_id,
            "subsections": subsection_ids,
        }

    # Helper to check if parent descends from Custom group of a given workspace
    def is_descendant_of_custom(node_id: str | None, ws_id: str) -> bool:
        if not node_id:
            return False
        curr_id = node_id.replace("-", "")
        visited = set()
        layout_custom = workspace_layouts.get(ws_id, {}).get("custom")
        if not layout_custom:
            return False
        while curr_id is not None:
            if curr_id in visited:
                break
            visited.add(curr_id)
            if curr_id == layout_custom:
                return True
            node = nodes_by_id.get(curr_id)
            if not node:
                break
            curr_id = node["parent_id"]
            if curr_id:
                curr_id = curr_id.replace("-", "")
        return False

    # Now, relocate children of workspaces and subtrees
    for n in all_nodes:
        nid = n["id"]
        # Skip workspace nodes and the System/Custom layout nodes themselves
        if n["node_kind"] in ("workspace", "system_group"):
            continue

        ws_id = find_workspace_id(nid)
        if not ws_id:
            continue

        layout = workspace_layouts[ws_id]

        if n["node_kind"] == "folder":
            # If folder's parent is directly the workspace, move it to Custom
            if n["parent_id"] == ws_id:
                connection.execute(
                    text("UPDATE nodes SET parent_id = :parent_id WHERE id = :id;"),
                    {"parent_id": layout["custom"], "id": nid},
                )
        elif n["node_kind"] == "resource":
            res_type = n["resource_type"] or "directory"
            if res_type == "reference":
                # Ensure it remains under Custom or a folder descending from Custom
                parent_id = n["parent_id"]
                if not is_descendant_of_custom(parent_id, ws_id):
                    # Invalid parent, move to Custom root of this workspace!
                    target_parent = layout["custom"]
                    if parent_id != target_parent:
                        connection.execute(
                            text(
                                "UPDATE nodes SET parent_id = :parent_id "
                                "WHERE id = :id;"
                            ),
                            {"parent_id": target_parent, "id": nid},
                        )
            else:
                role_map = {
                    "directory": "directories",
                    "file": "files",
                    "script": "scripts",
                    "executable": "executables",
                    "url": "urls",
                    "launch_profile": "launch_profiles",
                    "multi_launcher": "multi_launchers",
                }
                role = role_map.get(res_type, "directories")
                target_parent = layout["subsections"][role]

                if n["parent_id"] != target_parent:
                    connection.execute(
                        text("UPDATE nodes SET parent_id = :parent_id WHERE id = :id;"),
                        {"parent_id": target_parent, "id": nid},
                    )


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
