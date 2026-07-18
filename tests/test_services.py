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
    NodeNotFoundError,
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
    root1 = repo.create(
        Node(name="Root 1", node_kind="workspace", resource_type=None, sort_order=2)
    )
    root2 = repo.create(
        Node(name="Root 2", node_kind="workspace", resource_type=None, sort_order=1)
    )

    # Create children for root 2
    child1 = repo.create(
        Node(
            name="Child 1",
            node_kind="folder",
            resource_type=None,
            parent_id=root2.id,
            sort_order=2,
        )
    )
    child2 = repo.create(
        Node(
            name="Child 2",
            node_kind="folder",
            resource_type=None,
            parent_id=root2.id,
            sort_order=1,
        )
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
    root = repo.create(
        Node(name="Root", node_kind="workspace", resource_type=None, sort_order=1)
    )
    child_b = repo.create(
        Node(
            name="B",
            node_kind="folder",
            resource_type=None,
            parent_id=root.id,
            sort_order=2,
        )
    )
    child_a = repo.create(
        Node(
            name="A",
            node_kind="folder",
            resource_type=None,
            parent_id=root.id,
            sort_order=1,
        )
    )
    grandchild = repo.create(
        Node(
            name="Sub",
            node_kind="folder",
            resource_type=None,
            parent_id=child_a.id,
            sort_order=1,
        )
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
    root = repo.create(Node(name="Root", node_kind="folder", resource_type=None))
    child = repo.create(
        Node(
            name="Child",
            node_kind="folder",
            resource_type=None,
            parent_id=root.id,
        )
    )
    grandchild = repo.create(
        Node(
            name="Grandchild",
            node_kind="folder",
            resource_type=None,
            parent_id=child.id,
        )
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
    node_a = repo.create(
        Node(name="A", node_kind="folder", resource_type=None, parent_id=None)
    )
    node_b = repo.create(
        Node(name="B", node_kind="folder", resource_type=None, parent_id=None)
    )

    node_a.parent_id = node_b.id
    node_b.parent_id = node_a.id

    repo.update(node_a)
    repo.update(node_b)

    flat_nodes = repo.list_all()

    with pytest.raises(CycleError):
        node_service.build_tree(flat_nodes)


def test_resolve_path_for_nonexistent_node(node_service: NodeService) -> None:
    """Test that path resolution for an unknown node ID raises NodeNotFoundError."""
    with pytest.raises(NodeNotFoundError):
        node_service.resolve_node_path(uuid.uuid4())


def test_valid_directory_path_resolution(
    node_service: NodeService, session: Session
) -> None:
    """Test that a valid directory path is correctly resolved."""
    repo = node_service.repository

    with tempfile.TemporaryDirectory() as tmp_dir:
        resolved_tmp = Path(tmp_dir).resolve()
        node = repo.create(
            Node(
                name="Temp Dir",
                node_kind="resource",
                resource_type="directory",
                path=str(resolved_tmp),
            )
        )

        resolved_path = node_service.resolve_node_path(node.id)
        assert resolved_path == resolved_tmp


def test_missing_path(node_service: NodeService, session: Session) -> None:
    """Test that an error is raised when the node has no path."""
    repo = node_service.repository
    node = repo.create(
        Node(
            name="No Path Node",
            node_kind="resource",
            resource_type="directory",
            path=None,
        )
    )

    with pytest.raises(NoPathError):
        node_service.resolve_node_path(node.id)


def test_nonexistent_path(node_service: NodeService, session: Session) -> None:
    """Test that an error is raised when the path does not exist."""
    repo = node_service.repository
    nonexistent_p = "/nonexistent/path/for/pathtree/test"
    node = repo.create(
        Node(
            name="Bad Path Node",
            node_kind="resource",
            resource_type="directory",
            path=nonexistent_p,
        )
    )

    with pytest.raises(PathNotFoundError):
        node_service.resolve_node_path(node.id)


def test_path_pointing_to_file(node_service: NodeService, session: Session) -> None:
    """Test that an error is raised when the path points to a file, not a directory."""
    repo = node_service.repository

    with tempfile.NamedTemporaryFile() as tmp_file:
        node = repo.create(
            Node(
                name="File Path Node",
                node_kind="resource",
                resource_type="directory",
                path=tmp_file.name,
            )
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

    # Mock PathTreeApp.run so it doesn't start the interactive TUI in unit tests
    from pathtree.ui.app import PathTreeApp

    monkeypatch.setattr(PathTreeApp, "run", lambda self: None)

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


# --- Milestone 0.0.2 PR 2 Tests ---


def test_creation_valid_combinations(node_service: NodeService) -> None:
    """Test valid workspace, folder, and directory resource creation."""
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    assert ws.name == "My Workspace"
    assert ws.node_kind == "workspace"
    assert ws.resource_type is None

    folder = node_service.create_node(
        name="My Folder", node_kind="folder", parent_id=ws.id
    )
    assert folder.name == "My Folder"
    assert folder.node_kind == "folder"
    assert folder.parent_id == ws.id

    directory = node_service.create_node(
        name="My Dir",
        node_kind="resource",
        resource_type="directory",
        parent_id=folder.id,
        path="/some/unavailable/path",
    )
    assert directory.name == "My Dir"
    assert directory.node_kind == "resource"
    assert directory.resource_type == "directory"
    assert directory.path == "/some/unavailable/path"


def test_creation_empty_and_whitespace_names(node_service: NodeService) -> None:
    """Test empty and whitespace-only name rejections."""
    from pathtree.services.node_service import EmptyNodeNameError

    with pytest.raises(EmptyNodeNameError):
        node_service.create_node(name="", node_kind="workspace")

    with pytest.raises(EmptyNodeNameError):
        node_service.create_node(name="   ", node_kind="workspace")

    with pytest.raises(EmptyNodeNameError):
        node_service.create_node(name=None, node_kind="workspace")


def test_creation_invalid_combinations(node_service: NodeService) -> None:
    """Test invalid node-kind and resource-type combination rejection."""
    from pathtree.services.node_service import ValidationError

    with pytest.raises(ValidationError):
        node_service.create_node(
            name="Invalid", node_kind="workspace", resource_type="directory"
        )

    with pytest.raises(ValidationError):
        node_service.create_node(
            name="Invalid", node_kind="resource", resource_type="file"
        )


def test_creation_structural_node_with_path_rejection(
    node_service: NodeService,
) -> None:
    """Test structural workspace and folder nodes cannot have path."""
    from pathtree.services.node_service import ValidationError

    with pytest.raises(ValidationError):
        node_service.create_node(name="WS Path", node_kind="workspace", path="/etc")

    with pytest.raises(ValidationError):
        node_service.create_node(name="Folder Path", node_kind="folder", path="/tmp")


def test_creation_invalid_parent_rejections(node_service: NodeService) -> None:
    """Test invalid parent and resource parent rejections on creation."""
    from pathtree.services.node_service import (
        InvalidParentKindError,
        ParentNotFoundError,
    )

    # Nonexistent parent
    with pytest.raises(ParentNotFoundError):
        node_service.create_node(
            name="Test", node_kind="workspace", parent_id=uuid.uuid4()
        )

    # Resource parent (forbidden)
    res = node_service.create_node(
        name="Resource Parent", node_kind="resource", resource_type="directory"
    )
    with pytest.raises(InvalidParentKindError):
        node_service.create_node(name="Test", node_kind="folder", parent_id=res.id)


def test_creation_sibling_name_uniqueness(node_service: NodeService) -> None:
    """Test sibling name uniqueness with case and whitespace normalization."""
    from pathtree.services.node_service import DuplicateSiblingNameError

    # Root duplicates
    node_service.create_node(name="Assets", node_kind="workspace")

    with pytest.raises(DuplicateSiblingNameError):
        node_service.create_node(name=" assets ", node_kind="workspace")

    with pytest.raises(DuplicateSiblingNameError):
        node_service.create_node(name="ASSETS", node_kind="folder")

    # Sibling duplicates under a workspace
    ws = node_service.create_node(name="Projects", node_kind="workspace")
    node_service.create_node(name="Sub1", node_kind="folder", parent_id=ws.id)

    with pytest.raises(DuplicateSiblingNameError):
        node_service.create_node(name="SUB1", node_kind="folder", parent_id=ws.id)

    # Same name under different parents is allowed
    ws2 = node_service.create_node(name="Other Projects", node_kind="workspace")
    ok_node = node_service.create_node(
        name="Sub1", node_kind="folder", parent_id=ws2.id
    )
    assert ok_node is not None


def test_update_metadata_and_updated_at(node_service: NodeService) -> None:
    """Test successful metadata updates and updated_at advancement."""
    import time

    ws = node_service.create_node(name="Orig Name", node_kind="workspace")
    time.sleep(0.001)  # Ensure a tiny clock tick

    updated = node_service.update_node(
        ws.id,
        name="New Name",
        description="My description",
        icon="📁",
        sort_order=5,
        is_favorite=True,
    )

    assert updated.name == "New Name"
    assert updated.description == "My description"
    assert updated.icon == "📁"
    assert updated.sort_order == 5
    assert updated.is_favorite is True
    assert updated.updated_at > ws.created_at


def test_update_duplicate_sibling_rejection(node_service: NodeService) -> None:
    """Test updating a node name to match a sibling name is rejected."""
    from pathtree.services.node_service import DuplicateSiblingNameError

    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    node_service.create_node(name="FolderA", node_kind="folder", parent_id=ws.id)
    f_b = node_service.create_node(name="FolderB", node_kind="folder", parent_id=ws.id)

    with pytest.raises(DuplicateSiblingNameError):
        node_service.update_node(f_b.id, name=" FolderA ")


def test_update_temporary_and_permanent_rules(node_service: NodeService) -> None:
    """Test temporary/permanent promotion and demotion checks."""
    from pathtree.services.node_service import ValidationError

    # Temporary node can be promoted to permanent
    temp_node = node_service.create_node(
        name="Temp", node_kind="resource", is_temporary=True
    )
    assert temp_node.is_temporary is True

    promoted = node_service.update_node(temp_node.id, is_temporary=False)
    assert promoted.is_temporary is False

    # Permanent node cannot be demoted to temporary
    perm_node = node_service.create_node(
        name="Perm", node_kind="resource", is_temporary=False
    )
    with pytest.raises(ValidationError):
        node_service.update_node(perm_node.id, is_temporary=True)


def test_update_conversion_rejection(node_service: NodeService) -> None:
    """Test arbitrary conversions of node kind are rejected."""
    from pathtree.services.node_service import ValidationError

    ws = node_service.create_node(name="WS", node_kind="workspace")

    with pytest.raises(ValidationError):
        node_service.update_node(ws.id, node_kind="folder")

    with pytest.raises(ValidationError):
        node_service.update_node(ws.id, resource_type="directory")


def test_update_structural_path_rejection(node_service: NodeService) -> None:
    """Test structural nodes cannot have path updated on them."""
    from pathtree.services.node_service import ValidationError

    ws = node_service.create_node(name="WS", node_kind="workspace")

    with pytest.raises(ValidationError):
        node_service.update_node(ws.id, path="/home/user")


def test_move_node_scenarios(node_service: NodeService) -> None:
    """Test various valid and invalid moving scenarios."""
    from pathtree.services.node_service import (
        CycleError,
        DuplicateSiblingNameError,
        InvalidParentKindError,
        SelfParentError,
    )

    # Setup tree
    ws1 = node_service.create_node(name="WS1", node_kind="workspace")
    ws2 = node_service.create_node(name="WS2", node_kind="workspace")
    folder = node_service.create_node(
        name="Folder", node_kind="folder", parent_id=ws1.id
    )
    child = node_service.create_node(
        name="Child", node_kind="folder", parent_id=folder.id
    )
    res = node_service.create_node(name="Res", node_kind="resource", parent_id=ws1.id)

    # Move to root (parent_id = None)
    moved_root = node_service.move_node(folder.id, None)
    assert moved_root.parent_id is None

    # Move beneath workspace
    moved_ws = node_service.move_node(folder.id, ws2.id)
    assert moved_ws.parent_id == ws2.id

    # Move beneath folder
    moved_folder = node_service.move_node(child.id, folder.id)
    assert moved_folder.parent_id == folder.id

    # Reject resource as parent
    with pytest.raises(InvalidParentKindError):
        node_service.move_node(child.id, res.id)

    # Reject self-parenting
    with pytest.raises(SelfParentError):
        node_service.move_node(child.id, child.id)

    # Reject cycles (moving ancestor below descendant)
    with pytest.raises(CycleError):
        node_service.move_node(folder.id, child.id)

    # Sibling name clash in destination
    node_service.create_node(name="Child", node_kind="folder", parent_id=ws2.id)
    with pytest.raises(DuplicateSiblingNameError):
        node_service.move_node(child.id, ws2.id)

    # Failed moves leave original parent unchanged
    orig_parent_id = child.parent_id
    try:
        node_service.move_node(child.id, child.id)
    except SelfParentError:
        pass
    fresh_child = node_service.get_node(child.id)
    assert fresh_child.parent_id == orig_parent_id


def test_recursive_deletion_scenarios(node_service: NodeService) -> None:
    """Test leaf deletion, recursive deletion, and nonexistent node handling."""
    from pathtree.services.node_service import NodeNotFoundError

    # Setup tree
    ws = node_service.create_node(name="WS", node_kind="workspace")
    folder = node_service.create_node(
        name="Folder", node_kind="folder", parent_id=ws.id
    )
    node_service.create_node(name="Child1", node_kind="folder", parent_id=folder.id)
    node_service.create_node(name="Child2", node_kind="folder", parent_id=folder.id)

    # Test count descendants
    assert node_service.count_descendants(ws.id) == 3
    assert node_service.count_descendants(folder.id) == 2

    # Leaf deletion (non-recursive)
    leaf = node_service.create_node(name="Leaf", node_kind="folder")
    assert node_service.delete_node(leaf.id, recursive=False) is True
    assert node_service.get_node(leaf.id) is None

    # Deletion with children non-recursively raises error
    from pathtree.services.node_service import ValidationError

    with pytest.raises(ValidationError):
        node_service.delete_node(folder.id, recursive=False)

    # Deleting nonexistent node raises exception
    with pytest.raises(NodeNotFoundError):
        node_service.delete_node(uuid.uuid4())

    # Atomically delete container and descendants
    assert node_service.count_descendants(folder.id) == 2
    assert node_service.delete_node(folder.id, recursive=True) is True

    assert node_service.get_node(folder.id) is None
    assert node_service.count_descendants(ws.id) == 0


def test_recursive_deletion_rollback(
    node_service: NodeService, session: Session
) -> None:
    """Test complete transaction rollback on deletion failure."""
    # Setup tree
    ws = node_service.create_node(name="Rollback WS", node_kind="workspace")
    folder = node_service.create_node(
        name="Rollback Folder", node_kind="folder", parent_id=ws.id
    )

    # We monkeypatch session.delete on the folder's ID to raise an error
    orig_delete = session.delete

    def mock_delete(instance):
        if hasattr(instance, "name") and instance.name == "Rollback Folder":
            raise RuntimeError("Injected Deletion Failure")
        return orig_delete(instance)

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(session, "delete", mock_delete)
        with pytest.raises(RuntimeError, match="Injected Deletion Failure"):
            node_service.delete_node(ws.id, recursive=True)

    # Both must still exist because of transactional rollback!
    assert node_service.get_node(ws.id) is not None
    assert node_service.get_node(folder.id) is not None


def test_search_scenarios(node_service: NodeService) -> None:
    """Test tree-based search with type filters and ancestor chain preservation."""
    # Setup hierarchy:
    # Workspace: Project Alpha
    #   Folder: Src
    #     Resource: Main Dir (path: /alpha/src, description: Entrypoint folder)
    #   Folder: Tests
    # Workspace: Beta Project
    #   Folder: Src

    alpha = node_service.create_node(name="Project Alpha", node_kind="workspace")
    src_alpha = node_service.create_node(
        name="Src", node_kind="folder", parent_id=alpha.id
    )
    main_dir = node_service.create_node(
        name="Main Dir",
        node_kind="resource",
        resource_type="directory",
        parent_id=src_alpha.id,
        path="/alpha/src",
        description="Entrypoint folder",
    )
    node_service.create_node(name="Tests", node_kind="folder", parent_id=alpha.id)

    beta = node_service.create_node(name="Beta Project", node_kind="workspace")
    node_service.create_node(name="Src", node_kind="folder", parent_id=beta.id)

    # 1. Substring match on name (case-insensitive)
    results = node_service.search_nodes(query="alpha")
    # Should keep Alpha (matches), Src (ancestor of Main Dir or is child of Alpha),
    # Main Dir (matches /alpha/src in path), Tests (ancestor of nothing, matches name
    # 'Alpha' in root)
    # Let's count roots. Root Beta should be completely excluded.
    assert len(results) == 1
    assert results[0].node.id == alpha.id

    # 2. Substring match on path
    results_path = node_service.search_nodes(query="/alpha/src")
    assert len(results_path) == 1
    root = results_path[0]
    assert root.node.id == alpha.id
    assert root.children[0].node.id == src_alpha.id
    assert root.children[0].children[0].node.id == main_dir.id

    # 3. Substring match on description
    results_desc = node_service.search_nodes(query="entrypoint")
    assert len(results_desc) == 1
    assert results_desc[0].children[0].children[0].node.id == main_dir.id

    # 4. Filter by type:workspace
    results_ws = node_service.search_nodes(query="type:workspace")
    assert len(results_ws) == 2
    assert results_ws[0].node.id == alpha.id
    assert (
        len(results_ws[0].children) == 0
    )  # kids are not workspaces, so they are hidden
    assert results_ws[1].node.id == beta.id

    # 5. Filter by type:directory
    results_dir = node_service.search_nodes(query="type:directory")
    assert len(results_dir) == 1
    assert results_dir[0].node.id == alpha.id
    assert results_dir[0].children[0].children[0].node.id == main_dir.id

    # 6. Combined query: type:directory alpha
    results_combined = node_service.search_nodes(query="type:directory alpha")
    assert len(results_combined) == 1
    assert results_combined[0].children[0].children[0].node.id == main_dir.id

    # 7. No results
    assert len(node_service.search_nodes(query="xyzrandom")) == 0

    # 8. Empty query
    assert len(node_service.search_nodes(query="")) == 2
