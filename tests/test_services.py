import sys
import tempfile
import uuid
from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.app import main
from pathtree.database.connection import create_db_engine, init_db
from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import (
    CycleError,
    NodeService,
    NoPathError,
    ParentNotFoundError,
    PathNotADirectoryError,
    PathNotFoundError,
    SelfParentError,
)
from pathtree.services.seed import seed_development_data


@pytest.fixture(name="node_service")
def node_service_fixture(session: Session) -> NodeService:
    """Fixture for NodeService initialized with the test repository."""
    repo = NodeRepository(session)
    return NodeService(repo)


def test_empty_hierarchy(node_service: NodeService) -> None:
    """Test building a tree with an empty hierarchy list."""
    tree = node_service.build_tree([])
    assert tree == []


def test_root_and_child_loading(node_service: NodeService, session: Session) -> None:
    """Test loading root nodes and children nodes from repository."""
    repo = node_service.repository

    # Create root nodes
    root1 = repo.create(Node(name="Root 1", node_type="Workspace", sort_order=2))
    root2 = repo.create(Node(name="Root 2", node_type="Workspace", sort_order=1))

    # Create children for root 2
    child1 = repo.create(
        Node(name="Child 1", node_type="Folder", parent_id=root2.id, sort_order=2)
    )
    child2 = repo.create(
        Node(name="Child 2", node_type="Folder", parent_id=root2.id, sort_order=1)
    )

    # Test load_root_nodes (sorted by sort_order, then created_at)
    roots = node_service.load_root_nodes()
    assert len(roots) == 2
    assert roots[0].id == root2.id
    assert roots[1].id == root1.id

    # Test load_children
    children = node_service.load_children(root2.id)
    assert len(children) == 2
    assert children[0].id == child2.id
    assert children[1].id == child1.id

    # Non-existent children
    assert list(node_service.load_children(uuid.uuid4())) == []


def test_deterministic_nested_tree_construction(
    node_service: NodeService, session: Session
) -> None:
    """Test constructing a nested tree structure with repository order preserved."""
    repo = node_service.repository

    # Set up nodes with deterministic order
    root = repo.create(Node(name="Root", node_type="Workspace", sort_order=1))
    child_b = repo.create(
        Node(name="B", node_type="Folder", parent_id=root.id, sort_order=2)
    )
    child_a = repo.create(
        Node(name="A", node_type="Folder", parent_id=root.id, sort_order=1)
    )
    grandchild = repo.create(
        Node(name="Sub", node_type="Folder", parent_id=child_a.id, sort_order=1)
    )

    # Fetch flat list and build tree
    flat_nodes = repo.list_all()
    tree = node_service.build_tree(flat_nodes)

    assert len(tree) == 1
    root_node = tree[0]
    assert root_node.node.id == root.id

    # Children of Root should be [child_a, child_b] due to sort_order
    assert len(root_node.children) == 2
    assert root_node.children[0].node.id == child_a.id
    assert root_node.children[1].node.id == child_b.id

    # Grandchild should be child of child_a
    assert len(root_node.children[0].children) == 1
    assert root_node.children[0].children[0].node.id == grandchild.id
    assert len(root_node.children[1].children) == 0


def test_self_parent_rejection(node_service: NodeService) -> None:
    """Test that a node cannot be its own parent."""
    node_id = uuid.uuid4()
    with pytest.raises(SelfParentError):
        node_service.validate_parent(node_id, node_id)


def test_descendant_cycle_rejection(
    node_service: NodeService, session: Session
) -> None:
    """Test that moving a node below one of its descendants is rejected."""
    repo = node_service.repository

    # root -> child -> grandchild
    root = repo.create(Node(name="Root", node_type="Folder"))
    child = repo.create(Node(name="Child", node_type="Folder", parent_id=root.id))
    grandchild = repo.create(
        Node(name="Grandchild", node_type="Folder", parent_id=child.id)
    )

    # Validate setting grandchild as parent of root
    with pytest.raises(CycleError):
        node_service.validate_parent(root.id, grandchild.id)


def test_nonexistent_parent_rejection(node_service: NodeService) -> None:
    """Test that referencing a nonexistent parent node is rejected."""
    node_id = uuid.uuid4()
    nonexistent_id = uuid.uuid4()
    with pytest.raises(ParentNotFoundError):
        node_service.validate_parent(node_id, nonexistent_id)


def test_protection_against_malformed_cyclic_database_data(
    node_service: NodeService, session: Session
) -> None:
    """Test that malformed/cyclic DB data raises CycleError during build_tree."""
    repo = node_service.repository

    # Create nodes with parent_id=None initially to satisfy FK checks, then update them
    node_a = repo.create(Node(name="A", parent_id=None))
    node_b = repo.create(Node(name="B", parent_id=None))

    node_a.parent_id = node_b.id
    node_b.parent_id = node_a.id

    repo.update(node_a)
    repo.update(node_b)

    flat_nodes = repo.list_all()

    with pytest.raises(CycleError):
        node_service.build_tree(flat_nodes)


def test_valid_directory_path_resolution(
    node_service: NodeService, session: Session
) -> None:
    """Test that a valid directory path is correctly resolved."""
    repo = node_service.repository

    with tempfile.TemporaryDirectory() as tmp_dir:
        resolved_tmp = Path(tmp_dir).resolve()
        node = repo.create(
            Node(name="Temp Dir", node_type="Folder", path=str(resolved_tmp))
        )

        resolved_path = node_service.resolve_node_path(node.id)
        assert resolved_path == resolved_tmp


def test_missing_path(node_service: NodeService, session: Session) -> None:
    """Test that an error is raised when the node has no path."""
    repo = node_service.repository
    node = repo.create(Node(name="No Path Node", node_type="Folder", path=None))

    with pytest.raises(NoPathError):
        node_service.resolve_node_path(node.id)


def test_nonexistent_path(node_service: NodeService, session: Session) -> None:
    """Test that an error is raised when the path does not exist."""
    repo = node_service.repository
    nonexistent_p = "/nonexistent/path/for/pathtree/test"
    node = repo.create(
        Node(name="Bad Path Node", node_type="Folder", path=nonexistent_p)
    )

    with pytest.raises(PathNotFoundError):
        node_service.resolve_node_path(node.id)


def test_path_pointing_to_file(node_service: NodeService, session: Session) -> None:
    """Test that an error is raised when the path points to a file, not a directory."""
    repo = node_service.repository

    with tempfile.NamedTemporaryFile() as tmp_file:
        node = repo.create(
            Node(name="File Path Node", node_type="Folder", path=tmp_file.name)
        )

        with pytest.raises(PathNotADirectoryError):
            node_service.resolve_node_path(node.id)


def test_repeated_seeding_without_duplicates(session: Session) -> None:
    """Test that seeding is idempotent and does not create duplicates."""
    repo = NodeRepository(session)

    # Initial seed
    seed_development_data(repo)
    nodes_first_pass = repo.list_all()
    count_first = len(nodes_first_pass)
    assert count_first > 0

    # Repeated seed
    seed_development_data(repo)
    nodes_second_pass = repo.list_all()
    count_second = len(nodes_second_pass)

    assert count_first == count_second


def test_explicit_seed_dev_execution(monkeypatch, tmp_path: Path) -> None:
    """Test that --seed-dev executes correctly from the CLI."""
    db_file = tmp_path / "test_seed.db"
    monkeypatch.setenv("PATHTREE_DB_PATH", str(db_file))

    # Mock argv for CLI execution
    monkeypatch.setattr(sys, "argv", ["pathtree", "--seed-dev"])

    # Expecting exit code 0
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0

    # Check if DB file was created and contains seeded data
    engine = create_db_engine(db_file)
    init_db(engine)
    with Session(engine) as session:
        repo = NodeRepository(session)
        all_nodes = repo.list_all()
        assert len(all_nodes) > 0


def test_normal_cli_startup_not_creating_seed_data(monkeypatch, tmp_path: Path) -> None:
    """Test that normal CLI startup does not automatically seed database data."""
    db_file = tmp_path / "test_normal.db"
    monkeypatch.setenv("PATHTREE_DB_PATH", str(db_file))

    dummy_output = tmp_path / "dummy.txt"
    monkeypatch.setattr(sys, "argv", ["pathtree", "--output", str(dummy_output)])

    # Ensure no node table rows are seeded automatically
    with pytest.raises(SystemExit) as exc_info:
        main()

    assert exc_info.value.code == 0

    # Read nodes from the db
    engine = create_db_engine(db_file)
    init_db(engine)
    with Session(engine) as session:
        repo = NodeRepository(session)
        assert len(repo.list_all()) == 0
