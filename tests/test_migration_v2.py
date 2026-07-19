import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlmodel import Session, text

from pathtree.database.connection import (
    DatabaseMigrationError,
    UnsupportedDatabaseVersionError,
    create_db_engine,
    init_db,
)
from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService, ValidationError


def create_v1_db_with_test_data(db_path: Path):
    """Manually create a version 1 database using sqlite3 to populate legacy data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE nodes (
        id CHAR(32) NOT NULL,
        parent_id CHAR(32),
        name VARCHAR NOT NULL,
        node_type VARCHAR NOT NULL,
        description VARCHAR,
        icon VARCHAR,
        path VARCHAR,
        sort_order INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(parent_id) REFERENCES nodes (id)
    );
    """)
    cursor.execute("CREATE INDEX ix_nodes_parent_id ON nodes (parent_id);")
    cursor.execute("CREATE INDEX ix_nodes_name ON nodes (name);")
    cursor.execute("CREATE INDEX ix_nodes_id ON nodes (id);")
    cursor.execute("CREATE INDEX ix_nodes_node_type ON nodes (node_type);")
    cursor.execute("PRAGMA user_version = 1;")

    # Insert legacy records to verify conversion rules
    now_str = datetime.now(UTC).isoformat()
    id1 = uuid.uuid4().hex
    id2 = uuid.uuid4().hex
    id3 = uuid.uuid4().hex

    # 1. Workspace
    cursor.execute(
        "INSERT INTO nodes (id, parent_id, name, node_type, "
        "description, icon, path, sort_order, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            id1,
            None,
            "Workspace Node",
            "Workspace",
            "My workspace description",
            "💻",
            None,
            1,
            now_str,
            now_str,
        ),
    )
    # 2. Folder with empty path
    cursor.execute(
        "INSERT INTO nodes (id, parent_id, name, node_type, "
        "description, icon, path, sort_order, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            id2,
            id1,
            "Folder No Path",
            "Folder",
            "Folder desc",
            "📁",
            "",
            2,
            now_str,
            now_str,
        ),
    )
    # 3. Folder with non-empty path
    cursor.execute(
        "INSERT INTO nodes (id, parent_id, name, node_type, "
        "description, icon, path, sort_order, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            id3,
            id2,
            "Folder With Path",
            "Folder",
            "Folder with path desc",
            "📂",
            "/home/user/path",
            3,
            now_str,
            now_str,
        ),
    )
    conn.commit()
    conn.close()
    return id1, id2, id3


def test_fresh_database_creates_version_2(tmp_path):
    """Verify that a newly created database is initialized at version 2 directly."""
    db_file = tmp_path / "fresh_v2.db"
    engine = create_db_engine(db_file)
    init_db(engine)

    with Session(engine) as session:
        connection = session.connection()
        version = connection.execute(text("PRAGMA user_version;")).scalar()
        assert version == 2

        # Verify columns exist
        cursor = connection.execute(text("PRAGMA table_info(nodes);"))
        columns = [col[1] for col in cursor.fetchall()]
        assert "node_kind" in columns
        assert "resource_type" in columns
        assert "is_favorite" in columns
        assert "is_temporary" in columns

    engine.dispose()


def test_migration_v1_to_v2_conversion_rules(tmp_path):
    """Verify legacy data conversion and structural properties preservation."""
    db_file = tmp_path / "migration_v1_to_v2.db"
    id1, id2, id3 = create_v1_db_with_test_data(db_file)

    engine = create_db_engine(db_file)
    init_db(engine)

    with Session(engine) as session:
        connection = session.connection()
        # Verify version updated to 2
        version = connection.execute(text("PRAGMA user_version;")).scalar()
        assert version == 2

        # Verify idempotent indexes exist
        cursor = connection.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name LIKE 'ix_nodes_%';"
            )
        )
        indexes = [row[0] for row in cursor.fetchall()]
        assert "ix_nodes_node_kind" in indexes
        assert "ix_nodes_resource_type" in indexes
        assert "ix_nodes_is_favorite" in indexes
        assert "ix_nodes_is_temporary" in indexes

        # Retrieve migrated data using Node model via repository
        repo = NodeRepository(session)

        # Workspace Node (Workspace) -> workspace + None,
        # is_favorite=False, is_temporary=False
        node1 = repo.get_by_id(uuid.UUID(hex=id1))
        assert node1 is not None
        assert node1.name == "Workspace Node"
        assert node1.node_kind == "workspace"
        assert node1.resource_type is None
        assert node1.is_favorite is False
        assert node1.is_temporary is False
        assert node1.parent_id is None
        assert node1.description == "My workspace description"
        assert node1.icon == "💻"
        assert node1.sort_order == 1
        assert isinstance(node1.created_at, datetime)
        assert isinstance(node1.updated_at, datetime)

        # Folder Node without path (Folder) -> folder + None
        node2 = repo.get_by_id(uuid.UUID(hex=id2))
        assert node2 is not None
        assert node2.name == "Folder No Path"
        assert node2.node_kind == "folder"
        assert node2.resource_type is None
        assert node2.is_favorite is False
        assert node2.is_temporary is False
        assert node2.parent_id == node1.id
        assert node2.description == "Folder desc"
        assert node2.icon == "📁"
        assert node2.sort_order == 2

        # Folder Node with path (Folder) -> resource + directory
        node3 = repo.get_by_id(uuid.UUID(hex=id3))
        assert node3 is not None
        assert node3.name == "Folder With Path"
        assert node3.node_kind == "resource"
        assert node3.resource_type == "directory"
        assert node3.is_favorite is False
        assert node3.is_temporary is False
        assert node3.parent_id == node2.id
        assert node3.description == "Folder with path desc"
        assert node3.icon == "📂"
        assert node3.path == "/home/user/path"
        assert node3.sort_order == 3

    engine.dispose()


def test_repeated_version_2_startup_no_op(tmp_path):
    """Verify that repeated startup on a version 2 database is a clean no-op."""
    db_file = tmp_path / "repeated_startup.db"
    engine = create_db_engine(db_file)

    # First startup (creates fresh v2)
    init_db(engine)

    # Second and third startup (no-op)
    init_db(engine)
    init_db(engine)

    with Session(engine) as session:
        version = session.connection().execute(text("PRAGMA user_version;")).scalar()
        assert version == 2

    engine.dispose()


def test_newer_version_refusal(tmp_path):
    """Verify that a database with version > 2 is rejected and not modified."""
    db_file = tmp_path / "newer_version.db"

    # Create nodes table and set version to 3
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE nodes (id CHAR(32) PRIMARY KEY);")
    cursor.execute("PRAGMA user_version = 3;")
    conn.commit()
    conn.close()

    engine = create_db_engine(db_file)
    with pytest.raises(UnsupportedDatabaseVersionError) as excinfo:
        init_db(engine)
    assert "newer than the supported version 2" in str(excinfo.value)

    # Verify version remains 3 and table has not been altered/modified
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    version = cursor.execute("PRAGMA user_version;").fetchone()[0] or 0
    assert version == 3
    cursor.execute("PRAGMA table_info(nodes);")
    columns = [col[1] for col in cursor.fetchall()]
    assert len(columns) == 1
    assert columns[0] == "id"
    conn.close()
    engine.dispose()


class MockCursor:
    def __init__(self, original_cursor):
        self.original_cursor = original_cursor

    def execute(self, statement, *args, **kwargs):
        sql_str = str(statement)
        # We fail when adding indices or is_temporary to simulate mid-migration failure
        if "is_temporary" in sql_str or "ix_nodes_is_temporary" in sql_str:
            raise ValueError("Simulated migration failure midway")
        return self.original_cursor.execute(statement, *args, **kwargs)

    def close(self):
        self.original_cursor.close()

    def __getattr__(self, name):
        return getattr(self.original_cursor, name)


class MockDBAPIConnection:
    def __init__(self, real_conn):
        self.real_conn = real_conn

    def cursor(self, *args, **kwargs):
        real_cursor = self.real_conn.cursor(*args, **kwargs)
        return MockCursor(real_cursor)

    def rollback(self):
        self.real_conn.rollback()

    def commit(self):
        self.real_conn.commit()

    def close(self):
        self.real_conn.close()

    @property
    def dbapi_connection(self):
        return self


def test_migration_rollback_on_failure(tmp_path):
    """Verify complete transaction rollback after an injected migration failure."""
    from unittest import mock

    from sqlalchemy.engine import Connection

    db_file = tmp_path / "rollback_test.db"
    create_v1_db_with_test_data(db_file)

    engine = create_db_engine(db_file)

    # Mock Connection.connection descriptor to return our wrapper
    original_connection_property = Connection.connection

    @property
    def mock_connection_property(self):
        real_conn = original_connection_property.fget(self)
        return MockDBAPIConnection(real_conn)

    with mock.patch.object(Connection, "connection", mock_connection_property):
        with pytest.raises(DatabaseMigrationError):
            init_db(engine)

    # Now verify that database version is still 1 and new columns are NOT added
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    version = cursor.execute("PRAGMA user_version;").fetchone()[0] or 0
    assert version == 1

    # Verify columns in nodes table. It should NOT have node_kind or is_temporary.
    cursor.execute("PRAGMA table_info(nodes);")
    columns = [col[1] for col in cursor.fetchall()]
    assert "node_kind" not in columns
    assert "is_temporary" not in columns

    # Verify that existing data is still there and correct
    cursor.execute("SELECT count(*) FROM nodes;")
    assert cursor.fetchone()[0] == 3
    conn.close()
    engine.dispose()


def test_repository_round_trip(session):
    """Verify repository CRUD operations correctly read and write new fields."""
    repo = NodeRepository(session)

    node = Node(
        name="Round Trip Node",
        node_kind="resource",
        resource_type="directory",
        is_favorite=True,
        is_temporary=True,
        path="/tmp/path",
    )

    created = repo.create(node)
    assert created.id is not None
    assert created.node_kind == "resource"
    assert created.resource_type == "directory"
    assert created.is_favorite is True
    assert created.is_temporary is True

    # Fetch from repository
    fetched = repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.node_kind == "resource"
    assert fetched.resource_type == "directory"
    assert fetched.is_favorite is True
    assert fetched.is_temporary is True

    # Update fields
    fetched.is_favorite = False
    fetched.is_temporary = False
    fetched.node_kind = "workspace"
    fetched.resource_type = None

    updated = repo.update(fetched)
    assert updated.is_favorite is False
    assert updated.is_temporary is False
    assert updated.node_kind == "workspace"
    assert updated.resource_type is None

    # Fetch again
    fetched_again = repo.get_by_id(created.id)
    assert fetched_again.is_favorite is False
    assert fetched_again.is_temporary is False
    assert fetched_again.node_kind == "workspace"
    assert fetched_again.resource_type is None


def test_node_service_validation(session):
    """Verify NodeService validation of node_kind and resource_type combinations."""
    repo = NodeRepository(session)
    node_service = NodeService(repo)

    # Valid combinations:
    # 1. workspace + None
    n1 = Node(name="WS", node_kind="workspace", resource_type=None)
    node_service.validate_node(n1)  # Should not raise

    # 2. folder + None
    n2 = Node(name="Folder", node_kind="folder", resource_type=None)
    node_service.validate_node(n2)  # Should not raise

    # 3. resource + directory
    n3 = Node(name="Dir", node_kind="resource", resource_type="directory")
    node_service.validate_node(n3)  # Should not raise

    # Invalid combinations:
    # 4. workspace with resource_type
    n4 = Node(name="WS Invalid", node_kind="workspace", resource_type="directory")
    with pytest.raises(ValidationError) as excinfo:
        node_service.validate_node(n4)
    assert "Invalid combination" in str(excinfo.value)

    # 5. folder with resource_type
    n5 = Node(name="Folder Invalid", node_kind="folder", resource_type="directory")
    with pytest.raises(ValidationError):
        node_service.validate_node(n5)

    # 6. resource with null resource_type
    n6 = Node(name="Resource Invalid", node_kind="resource", resource_type=None)
    with pytest.raises(ValidationError):
        node_service.validate_node(n6)

    # 7. completely invalid kind/resource_type
    n7 = Node(
        name="Total Invalid", node_kind="invalid_kind", resource_type="invalid_type"
    )
    with pytest.raises(ValidationError):
        node_service.validate_node(n7)


def test_unsupported_version_no_table_creation(tmp_path):
    """Verify that a database with version > 2 is rejected early.

    Even when there is no nodes table present.
    """
    db_file = tmp_path / "newer_version_no_table.db"

    # Create empty db with version 3
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    cursor.execute("PRAGMA user_version = 3;")
    conn.commit()
    conn.close()

    engine = create_db_engine(db_file)
    with pytest.raises(UnsupportedDatabaseVersionError) as excinfo:
        init_db(engine)
    assert "newer than the supported version 2" in str(excinfo.value)

    # Verify version remains 3 and nodes table was NOT created
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    version = cursor.execute("PRAGMA user_version;").fetchone()[0] or 0
    assert version == 3

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='nodes';"
    )
    assert cursor.fetchone() is None
    conn.close()
    engine.dispose()


def test_create_node_without_legacy_node_type(session):
    """Verify that creating nodes does not require callers to provide legacy node_type.

    This ensures domain code is not coupled to the deprecated column.
    """
    repo = NodeRepository(session)

    # 1. Workspace
    n1 = Node(name="My Workspace", node_kind="workspace")
    created1 = repo.create(n1)
    assert created1.legacy_node_type == "Workspace"  # mapped deterministically

    # 2. Folder
    n2 = Node(name="My Folder", node_kind="folder")
    created2 = repo.create(n2)
    assert created2.legacy_node_type == "Folder"

    # 3. Resource directory
    n3 = Node(name="My Resource", node_kind="resource", resource_type="directory")
    created3 = repo.create(n3)
    assert created3.legacy_node_type == "Folder"


def test_migration_v2_regression_not_null_no_default_node_type(tmp_path):
    """Regression test with legacy v1 DB (node_type is NOT NULL with no default)."""
    import sqlite3

    db_file = tmp_path / "legacy_regression.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # Create the v1 table where node_type is NOT NULL and has NO default
    cursor.execute("""
    CREATE TABLE nodes (
        id CHAR(32) NOT NULL,
        parent_id CHAR(32),
        name VARCHAR NOT NULL,
        node_type VARCHAR NOT NULL,
        description VARCHAR,
        icon VARCHAR,
        path VARCHAR,
        sort_order INTEGER NOT NULL,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(parent_id) REFERENCES nodes (id)
    );
    """)
    cursor.execute("PRAGMA user_version = 1;")
    conn.commit()
    conn.close()

    # Run the migration to v2
    engine = create_db_engine(db_file)
    init_db(engine)

    # Verify migration successful, then create all kinds via NodeService
    with Session(engine) as session:
        repo = NodeRepository(session)
        service = NodeService(repo)

        # - Workspace
        ws = service.create_node(name="Workspace Node", node_kind="workspace")
        assert ws.id is not None
        assert ws.node_kind == "workspace"
        assert ws.resource_type is None
        assert ws.legacy_node_type == "Workspace"

        # - Folder
        folder = service.create_node(
            name="Folder Node", node_kind="folder", parent_id=ws.id
        )
        assert folder.id is not None
        assert folder.node_kind == "folder"
        assert folder.resource_type is None
        assert folder.legacy_node_type == "Folder"

        # - Directory resource
        res = service.create_node(
            name="Directory Node",
            node_kind="resource",
            resource_type="directory",
            parent_id=folder.id,
            path="/tmp/test_dir",
        )
        assert res.id is not None
        assert res.node_kind == "resource"
        assert res.resource_type == "directory"
        assert res.legacy_node_type == "Folder"

    engine.dispose()
