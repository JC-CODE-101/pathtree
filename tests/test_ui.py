"""TUI layout and navigation tests."""

from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp


@pytest.mark.asyncio
async def test_empty_database_rendering(session: Session) -> None:
    """Test that an empty database renders gracefully without errors."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        assert len(tree.root.children) == 0

        details = app.screen.query_one("#details-panel")
        assert "No nodes yet" in details.render().plain


@pytest.mark.asyncio
async def test_nested_tree_rendering_and_order(session: Session) -> None:
    """Test that nested tree structure is correctly rendered in order."""
    repo = NodeRepository(session)
    repo.create(Node(name="Root 1", sort_order=2))
    root2 = repo.create(Node(name="Root 2", sort_order=1))
    repo.create(Node(name="Child 1", parent_id=root2.id, sort_order=2))
    repo.create(Node(name="Child 2", parent_id=root2.id, sort_order=1))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Root nodes ordered by sort_order
        assert len(tree.root.children) == 2
        assert str(tree.root.children[0].label) == "Root 2"
        assert str(tree.root.children[1].label) == "Root 1"

        # Children of Root 2 ordered by sort_order
        root2_tree_node = tree.root.children[0]
        assert len(root2_tree_node.children) == 2
        assert str(root2_tree_node.children[0].label) == "Child 2"
        assert str(root2_tree_node.children[1].label) == "Child 1"


@pytest.mark.asyncio
async def test_keyboard_navigation_and_expansion(session: Session) -> None:
    """Test keyboard navigation, node expansion/collapsing, and details update."""
    repo = NodeRepository(session)
    root = repo.create(Node(name="Root", sort_order=1, description="Top workspace"))
    repo.create(
        Node(name="Child", parent_id=root.id, sort_order=1, description="Sub folder")
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        details = app.screen.query_one("#details-panel")

        # Initial focus should be on the first root node
        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "Root"
        assert "Top workspace" in details.render().plain

        # Expand Root node
        await pilot.press("l")
        assert tree.cursor_node.is_expanded is True

        # Move cursor down to Child node
        await pilot.press("j")
        assert str(tree.cursor_node.label) == "Child"
        assert "Sub folder" in details.render().plain

        # Move cursor up to Root node
        await pilot.press("k")
        assert str(tree.cursor_node.label) == "Root"

        # Collapse and parent test
        # Change focus to Child
        await pilot.press("j")
        # Collapse/Parent key should go up to Root
        await pilot.press("h")
        assert str(tree.cursor_node.label) == "Root"

        # Collapse Root
        await pilot.press("h")
        assert tree.cursor_node.is_expanded is False


@pytest.mark.asyncio
async def test_valid_enter_activation(session: Session, tmp_path: Path) -> None:
    """Test that Enter on a node with a valid path writes to output."""
    repo = NodeRepository(session)
    valid_dir = tmp_path / "valid_dir"
    valid_dir.mkdir()
    repo.create(Node(name="Root", path=str(valid_dir), sort_order=1))

    output_file = tmp_path / "selected.txt"

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("enter")

        # Wait for app to exit
        while app.return_code is None:
            await pilot.pause(0.01)

        assert output_file.exists()
        written_path = output_file.read_text(encoding="utf-8").strip()
        assert Path(written_path).resolve() == valid_dir.resolve()
        assert app.return_code == 0


@pytest.mark.asyncio
async def test_invalid_enter_activation_does_not_exit(
    session: Session, tmp_path: Path
) -> None:
    """Test that invalid node activation shows error in UI and does not close app."""
    repo = NodeRepository(session)
    invalid_file = tmp_path / "some_file.txt"
    invalid_file.write_text("not a dir", encoding="utf-8")
    repo.create(Node(name="Root", path=str(invalid_file), sort_order=1))

    output_file = tmp_path / "selected.txt"

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("enter")

        # Output file should NOT be written
        assert not output_file.exists()

        # App should still be running / not exited
        assert app.return_code is None

        # Details panel should render the error
        details = app.screen.query_one("#details-panel")
        assert "Error" in details.render().plain


@pytest.mark.asyncio
async def test_q_exits_safely(session: Session) -> None:
    """Test that pressing q exits the application safely."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("q")

        # Wait for app to exit
        while app.return_code is None:
            await pilot.pause(0.01)

        assert app.return_code == 0


@pytest.mark.asyncio
async def test_cyclic_database_handled_gracefully(session: Session) -> None:
    """Test that database cycle error is handled gracefully on startup."""
    repo = NodeRepository(session)
    node_a = repo.create(Node(name="A", parent_id=None))
    node_b = repo.create(Node(name="B", parent_id=None))

    node_a.parent_id = node_b.id
    node_b.parent_id = node_a.id

    repo.update(node_a)
    repo.update(node_b)

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # The tree view should be empty
        tree = app.screen.query_one("#tree-view")
        assert len(tree.root.children) == 0

        # The details panel should display the cycle error message
        details = app.screen.query_one("#details-panel")
        assert "Cycle detected" in details.render().plain


@pytest.mark.asyncio
async def test_enter_activation_without_output_file(
    session: Session, tmp_path: Path
) -> None:
    """Test that Enter on a node without an output file specified does not exit."""
    repo = NodeRepository(session)
    valid_dir = tmp_path / "valid_dir"
    valid_dir.mkdir()
    repo.create(Node(name="Root", path=str(valid_dir), sort_order=1))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=None)
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("enter")

        # App should still be running / not exited
        assert app.return_code is None

        # Details panel should display the error about missing output file
        details = app.screen.query_one("#details-panel")
        assert "No output file specified" in details.render().plain


@pytest.mark.asyncio
async def test_search_ui_and_filtering(session: Session, tmp_path: Path) -> None:
    """Test full UI SearchInput layout, filtering, and type filters."""
    repo = NodeRepository(session)
    # Seeding database
    workspace_node = repo.create(
        Node(
            name="My Workspace",
            node_kind="workspace",
            resource_type=None,
            sort_order=1,
            description="Active developer workspace",
        )
    )
    folder_node = repo.create(
        Node(
            name="Nested Folder",
            node_kind="folder",
            resource_type=None,
            parent_id=workspace_node.id,
            sort_order=1,
            description="Folder description text",
        )
    )
    repo.create(
        Node(
            name="Specific Target Dir",
            node_kind="resource",
            resource_type="directory",
            parent_id=folder_node.id,
            path="/tmp/my-target",
            sort_order=1,
            description="Specific target description",
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        # Wait for main screen to load
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # 1. Verify Layout
        search_input = app.screen.query_one("#search-input")
        assert search_input is not None
        assert "Search nodes" in search_input.placeholder

        tree = app.screen.query_one("#tree-view")
        details = app.screen.query_one("#details-panel")
        assert tree is not None
        assert details is not None

        # 2. Focus transitions: '/' focuses search from tree
        assert app.screen.focused == tree
        await pilot.press("/")
        assert app.screen.focused == search_input

        # Escape from search input clears search and returns focus to tree
        search_input.value = "target"
        await pilot.pause(0.01)
        # Verify filtering worked:
        # My Workspace -> Nested Folder -> Specific Target Dir
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "My Workspace"

        await pilot.press("escape")
        assert search_input.value == ""
        assert app.screen.focused == tree

        # Focus via 's' key
        await pilot.press("s")
        assert app.screen.focused == search_input

        # Down from search input focuses tree
        await pilot.press("down")
        assert app.screen.focused == tree

        # Enter from search input focuses tree but doesn't activate immediately
        await pilot.press("s")
        assert app.screen.focused == search_input
        await pilot.press("enter")
        assert app.screen.focused == tree
        assert app.return_code is None

        # 3. Filtering by name, path, and description
        await pilot.press("s")
        # Substring search is case-insensitive
        for char in "SPECIFIC":
            await pilot.press(char.lower())
        await pilot.pause(0.01)
        assert search_input.value == "specific"
        # Tree should only contain matched descendant and its ancestors
        assert len(tree.root.children) == 1
        root_child = tree.root.children[0]
        assert str(root_child.label) == "My Workspace"

        # Search by path
        await pilot.press("escape")
        await pilot.press("s")
        for char in "target":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1

        # Search by description
        await pilot.press("escape")
        await pilot.press("s")
        for char in "active":
            await pilot.press(char)
        await pilot.pause(0.01)
        # Should match "My Workspace" since its description has "active"
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "My Workspace"

        # 4. Type filters
        # type:workspace
        await pilot.press("escape")
        await pilot.press("s")
        for char in "type:workspace":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "My Workspace"

        # type:folder
        await pilot.press("escape")
        await pilot.press("s")
        for char in "type:folder":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1
        # Root contains "My Workspace" because it's the ancestor of
        # "Nested Folder" (type:folder)
        assert str(tree.root.children[0].label) == "My Workspace"

        # type:directory
        await pilot.press("escape")
        await pilot.press("s")
        for char in "type:directory":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1

        # Combined text + type filter
        await pilot.press("escape")
        await pilot.press("s")
        for char in "specific type:directory":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1

        # No matches state
        await pilot.press("escape")
        await pilot.press("s")
        for char in "xyzabc123":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 0
        assert "No matching nodes" in details.render().plain

        # Clearing restores tree and selection
        await pilot.press("escape")
        assert len(tree.root.children) == 1
        assert "Active developer workspace" in details.render().plain
