import os
import tempfile
import uuid
from pathlib import Path

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
    """Test user_version is correctly queried and set to 1."""
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
            assert version == 1

            # Check that table exists
            cursor = connection.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='nodes';"
                )
            )
            assert cursor.first() is not None

        # Re-run init_db and ensure version is still 1
        init_db(engine)
        with Session(engine) as session:
            connection = session.connection()
            version = connection.execute(text("PRAGMA user_version;")).scalar()
            assert version == 1

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
    """Test creating a Node and optional local path attribute."""
    repo = NodeRepository(session)

    node = Node(
        name="My Workspace",
        node_type="Workspace",
        description="Core developer projects",
        icon="📁",
        path="/home/user/projects",
        sort_order=5,
    )

    created = repo.create(node)

    assert created.id is not None
    assert isinstance(created.id, uuid.UUID)
    assert created.name == "My Workspace"
    assert created.node_type == "Workspace"
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
    root = repo.create(Node(name="Root", node_type="Workspace", sort_order=1))
    # Create children
    child1 = repo.create(
        Node(name="Child 1", node_type="Folder", parent_id=root.id, sort_order=2)
    )
    child2 = repo.create(
        Node(name="Child 2", node_type="Folder", parent_id=root.id, sort_order=1)
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

    node = repo.create(Node(name="Old Name", node_type="Folder", path="/original"))

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

    node = repo.create(Node(name="To Delete", node_type="Folder"))
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
