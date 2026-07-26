import os
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlmodel import Session, text

from pathtree.database.connection import (
    create_db_engine,
    get_db_path,
    init_db,
)
from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node


def test_get_db_path(monkeypatch):
    """Test get_db_path platform-compliant path and env override."""
    # Test env override
    monkeypatch.setenv("PATHTREE_DB_PATH", "/tmp/custom_pathtree.db")
    assert get_db_path() == Path("/tmp/custom_pathtree.db")

    # Test default platformdirs path
    monkeypatch.delenv("PATHTREE_DB_PATH", raising=False)
    db_path = get_db_path()
    assert "pathtree" in str(db_path)
    assert db_path.name == "pathtree.db"


def test_sqlite_pragmas(engine):
    """Test WAL and foreign keys are enabled."""
    with Session(engine) as session:
        connection = session.connection()

        # Foreign keys check
        fk = connection.execute(text("PRAGMA foreign_keys;")).scalar()
        assert fk in (1, "on", True)

        # Note: SQLite on :memory: might report 'memory' or 'wal' for journal_mode
        jm = connection.execute(text("PRAGMA journal_mode;")).scalar()
        assert jm in ("wal", "memory")


def test_user_version():
    """Test user_version is correctly queried and set to 3."""
    # Use a temp file to ensure clean initialization behavior
    fd, temp_path_str = tempfile.mkstemp()
    os.close(fd)
    temp_path = Path(temp_path_str)

    try:
        engine = create_db_engine(temp_path)
        init_db(engine)

        # Check user_version and tables
        with Session(engine) as session:
            connection = session.connection()
            version = connection.execute(text("PRAGMA user_version;")).scalar()
            assert version == 3

            # Check that table exists
            cursor = connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='nodes';"
                )
            )
            assert cursor.first() is not None

        # Re-run init_db and ensure version is still 3
        init_db(engine)
        with Session(engine) as session:
            connection = session.connection()
            version = connection.execute(text("PRAGMA user_version;")).scalar()
            assert version == 3

    finally:
        if temp_path.exists():
            # Close the engine to let go of file handles.
            engine.dispose()
            try:
                temp_path.unlink()
            except OSError:
                pass
            # clean up WAL files if any
            for suffix in ("-wal", "-shm"):
                p = Path(str(temp_path) + suffix)
                if p.exists():
                    try:
                        p.unlink()
                    except OSError:
                        pass


def test_node_create(session):
    """Test creating a Node with node_kind and resource_type."""
    repo = NodeRepository(session)

    node = Node(
        name="My Directory",
        node_kind="resource",
        resource_type="directory",
        description="Core developer projects",
        icon="📁",
        path="/home/user/projects",
        sort_order=5,
    )

    created = repo.create(node)

    assert created.id is not None
    assert isinstance(created.id, uuid.UUID)
    assert created.name == "My Directory"
    assert created.node_kind == "resource"
    assert created.resource_type == "directory"
    assert created.description == "Core developer projects"
    assert created.icon == "📁"
    assert created.path == "/home/user/projects"
    assert created.sort_order == 5
    assert created.created_at is not None
    assert created.updated_at is not None


def test_node_read(session):
    """Test reading Node (get_by_id, list_all, list_children)."""
    repo = NodeRepository(session)

    # Create root
    root = repo.create(
        Node(name="Root", node_kind="workspace", resource_type=None, sort_order=1)
    )
    # Create children
    child1 = repo.create(
        Node(
            name="Child 1",
            node_kind="folder",
            resource_type=None,
            parent_id=root.id,
            sort_order=2,
        )
    )
    child2 = repo.create(
        Node(
            name="Child 2",
            node_kind="folder",
            resource_type=None,
            parent_id=root.id,
            sort_order=1,
        )
    )

    # Test get_by_id
    fetched_root = repo.get_by_id(root.id)
    assert fetched_root is not None
    assert fetched_root.name == "Root"

    # Test get_by_id on non-existent
    assert repo.get_by_id(uuid.uuid4()) is None

    # Test list_all (should order by sort_order)
    all_nodes = repo.list_all()
    assert len(all_nodes) == 3
    # root (sort_order 1), child2 (sort_order 1, parent root), child1 (sort_order 2)
    # Let's verify sorted order: sort_order, then created_at
    assert all_nodes[0].name == "Root"
    assert all_nodes[1].name == "Child 2"
    assert all_nodes[2].name == "Child 1"

    # Test list_children
    children = repo.list_children(root.id)
    assert len(children) == 2
    # Should sort by sort_order
    assert children[0].id == child2.id
    assert children[1].id == child1.id

    # Test list_children for root level (parent_id is None)
    root_level = repo.list_children(None)
    assert len(root_level) == 1
    assert root_level[0].id == root.id


def test_node_update(session):
    """Test updating an existing Node."""
    repo = NodeRepository(session)

    node = repo.create(
        Node(
            name="Old Name",
            node_kind="resource",
            resource_type="directory",
            path="/original",
        )
    )

    # Update attributes
    node.name = "New Name"
    node.path = "/new_path"
    updated = repo.update(node)

    assert updated.id == node.id
    assert updated.name == "New Name"
    assert updated.path == "/new_path"

    # Fetch and verify
    fetched = repo.get_by_id(node.id)
    assert fetched.name == "New Name"
    assert fetched.path == "/new_path"


def test_node_delete(session):
    """Test deleting a Node."""
    repo = NodeRepository(session)

    node = repo.create(Node(name="To Delete", node_kind="folder", resource_type=None))
    node_id = node.id

    # Verify exists
    assert repo.get_by_id(node_id) is not None

    # Delete
    deleted = repo.delete(node_id)
    assert deleted is True

    # Verify doesn't exist
    assert repo.get_by_id(node_id) is None

    # Delete non-existent
    assert repo.delete(uuid.uuid4()) is False


def test_platformdirs_dependency():
    """Verify platformdirs is explicitly specified in pyproject.toml."""
    import tomllib

    pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)
    deps = data.get("project", {}).get("dependencies", [])
    assert "platformdirs" in deps


def test_engine_pragma_isolation():
    """Verify connection PRAGMAs are applied only to engines from create_db_engine.

    Ensures they are not registered globally on other SQLAlchemy engines.
    """
    from sqlalchemy import create_engine as raw_create_engine

    # 1. Unrelated engine - should NOT have WAL/foreign keys configured automatically
    unrelated_engine = raw_create_engine("sqlite://")
    with Session(unrelated_engine) as session:
        connection = session.connection()
        fk = connection.execute(text("PRAGMA foreign_keys;")).scalar()
        assert fk == 0

    # 2. PathTree engine - should be configured with WAL and foreign keys
    pathtree_engine = create_db_engine(Path(":memory:"))
    with Session(pathtree_engine) as session:
        connection = session.connection()
        fk = connection.execute(text("PRAGMA foreign_keys;")).scalar()
        assert fk == 1


def test_updated_at_increases_on_update(session):
    """Verify that updated_at increases when a Node is updated."""
    import time

    repo = NodeRepository(session)

    node = repo.create(Node(name="Test Node", node_kind="folder", resource_type=None))
    original_updated_at = node.updated_at

    # Wait briefly to ensure a timestamp difference
    time.sleep(0.01)

    node.name = "Modified Name"
    updated_node = repo.update(node)

    assert updated_node.updated_at > original_updated_at


def test_repository_transaction_safety_and_rollback(session):
    """Verify failed create/update operations rollback and keep session usable."""
    from pathtree.database.errors import RepositoryIntegrityError

    repo = NodeRepository(session)

    # 1. Create a valid node
    node1 = repo.create(Node(name="Node 1", node_kind="folder"))
    assert node1.id is not None

    # 2. Force an IntegrityError during create (duplicate UUID)
    node_dup = Node(id=node1.id, name="Node Duplicate", node_kind="folder")
    with pytest.raises(RepositoryIntegrityError) as excinfo:
        repo.create(node_dup)
    assert "Database persistence violated integrity" in str(excinfo.value)

    # 3. Verify session remains usable by inserting a new valid node
    node2 = repo.create(Node(name="Node 2", node_kind="folder"))
    assert node2.id is not None
    assert node2.id != node1.id

    # 4. Force an IntegrityError during update (violating NOT NULL name constraint)
    # SQLite does not allow null name
    node2.name = None
    with pytest.raises(RepositoryIntegrityError) as excinfo:
        repo.update(node2)
    assert "Database update violated integrity" in str(excinfo.value)

    # 5. Restore node2 name and verify update succeeds to prove session is still usable
    node2.name = "Node 2 Restored"
    updated = repo.update(node2)
    assert updated.name == "Node 2 Restored"
