"""TUI layout, navigation, and interactive management tests."""

import uuid
from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.dialogs.confirm_delete import ConfirmDeleteDialog
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.dialogs.move_node import MoveNodeDialog


@pytest.mark.asyncio
async def test_empty_database_rendering(session: Session) -> None:
    """Test that an empty database renders gracefully without errors."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
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
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        assert len(tree.root.children) == 2
        assert str(tree.root.children[0].label) == "Root 2"
        assert str(tree.root.children[1].label) == "Root 1"

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
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        details = app.screen.query_one("#details-panel")

        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "Root"
        assert "Top workspace" in details.render().plain

        await pilot.press("l")
        assert tree.cursor_node.is_expanded is True

        await pilot.press("j")
        assert str(tree.cursor_node.label) == "Child"
        assert "Sub folder" in details.render().plain

        await pilot.press("k")
        assert str(tree.cursor_node.label) == "Root"

        await pilot.press("j")
        await pilot.press("h")
        assert str(tree.cursor_node.label) == "Root"

        await pilot.press("h")
        assert tree.cursor_node.is_expanded is False


@pytest.mark.asyncio
async def test_valid_enter_activation(session: Session, tmp_path: Path) -> None:
    """Test that Enter on a node with a valid path writes to output."""
    repo = NodeRepository(session)
    valid_dir = tmp_path / "valid_dir"
    valid_dir.mkdir()
    repo.create(
        Node(
            name="Root",
            path=str(valid_dir),
            sort_order=1,
            node_kind="resource",
            resource_type="directory",
        )
    )

    output_file = tmp_path / "selected.txt"

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("enter")

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
    repo.create(
        Node(
            name="Root",
            path=str(invalid_file),
            sort_order=1,
            node_kind="resource",
            resource_type="directory",
        )
    )

    output_file = tmp_path / "selected.txt"

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("enter")

        assert not output_file.exists()
        assert app.return_code is None

        details = app.screen.query_one("#details-panel")
        assert "Error" in details.render().plain


@pytest.mark.asyncio
async def test_q_exits_safely(session: Session) -> None:
    """Test that pressing q exits the application safely."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("q")

        while app.return_code is None:
            await pilot.pause(0.01)

        assert app.return_code == 0


@pytest.mark.asyncio
async def test_ctrl_q_exits_safely(session: Session) -> None:
    """Test that pressing ctrl+q exits the application safely and cleanly."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("ctrl+q")

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
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        assert len(tree.root.children) == 0

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
    repo.create(
        Node(
            name="Root",
            path=str(valid_dir),
            sort_order=1,
            node_kind="resource",
            resource_type="directory",
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=None)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("enter")

        assert app.return_code is None

        details = app.screen.query_one("#details-panel")
        assert "No output file specified" in details.render().plain


@pytest.mark.asyncio
async def test_search_ui_and_filtering(session: Session, tmp_path: Path) -> None:
    """Test full UI SearchInput layout, filtering, and type filters."""
    repo = NodeRepository(session)
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
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        search_input = app.screen.query_one("#search-input")
        assert search_input is not None
        assert "Search nodes" in search_input.placeholder

        tree = app.screen.query_one("#tree-view")
        details = app.screen.query_one("#details-panel")
        assert tree is not None
        assert details is not None

        assert app.screen.focused == tree
        await pilot.press("/")
        assert app.screen.focused == search_input

        search_input.value = "target"
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "My Workspace"

        await pilot.press("escape")
        assert search_input.value == ""
        assert app.screen.focused == tree

        await pilot.press("s")
        assert app.screen.focused == search_input

        await pilot.press("down")
        assert app.screen.focused == tree

        await pilot.press("s")
        assert app.screen.focused == search_input
        await pilot.press("enter")
        assert app.screen.focused == tree
        assert app.return_code is None

        await pilot.press("s")
        for char in "SPECIFIC":
            await pilot.press(char.lower())
        await pilot.pause(0.01)
        assert search_input.value == "specific"
        assert len(tree.root.children) == 1
        root_child = tree.root.children[0]
        assert str(root_child.label) == "My Workspace"

        await pilot.press("escape")
        await pilot.press("s")
        for char in "target":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1

        await pilot.press("escape")
        await pilot.press("s")
        for char in "active":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "My Workspace"

        await pilot.press("escape")
        await pilot.press("s")
        for char in "type:workspace":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "My Workspace"

        await pilot.press("escape")
        await pilot.press("s")
        for char in "type:folder":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1
        assert str(tree.root.children[0].label) == "My Workspace"

        await pilot.press("escape")
        await pilot.press("s")
        for char in "type:directory":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1

        await pilot.press("escape")
        await pilot.press("s")
        for char in "specific type:directory":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 1

        await pilot.press("escape")
        await pilot.press("s")
        for char in "xyzabc123":
            await pilot.press(char)
        await pilot.pause(0.01)
        assert len(tree.root.children) == 0
        assert "No matching nodes" in details.render().plain

        await pilot.press("escape")
        assert len(tree.root.children) == 1
        assert "Active developer workspace" in details.render().plain


@pytest.mark.asyncio
async def test_pre_search_selection_restored(session: Session) -> None:
    """Test that Escape restores the selection that existed before search started."""
    repo = NodeRepository(session)
    node_a = repo.create(Node(name="Apple Node", sort_order=1))
    node_b = repo.create(Node(name="Banana Node", sort_order=2))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        await pilot.press("j")
        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "Banana Node"
        assert tree.cursor_node.data == node_b.id

        await pilot.press("/")
        for char in "apple":
            await pilot.press(char)
        await pilot.pause(0.01)

        assert len(tree.root.children) == 1
        assert str(tree.cursor_node.label) == "Apple Node"
        assert tree.cursor_node.data == node_a.id

        await pilot.press("escape")
        await pilot.pause(0.01)

        assert len(tree.root.children) == 2
        assert str(tree.cursor_node.label) == "Banana Node"
        assert tree.cursor_node.data == node_b.id


@pytest.mark.asyncio
async def test_selection_preserved_when_visible(session: Session) -> None:
    """Test that a selected node remains selected when it still matches search."""
    repo = NodeRepository(session)
    node_a = repo.create(Node(name="Apple Core", sort_order=1))
    repo.create(Node(name="Banana Peel", sort_order=2))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "Apple Core"
        assert tree.cursor_node.data == node_a.id

        await pilot.press("/")
        for char in "apple":
            await pilot.press(char)
        await pilot.pause(0.01)

        assert len(tree.root.children) == 1
        assert str(tree.cursor_node.label) == "Apple Core"
        assert tree.cursor_node.data == node_a.id


@pytest.mark.asyncio
async def test_empty_database_search_state(session: Session) -> None:
    """Test empty database shows 'No nodes yet' even during non-empty search."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        details = app.screen.query_one("#details-panel")

        assert len(tree.root.children) == 0
        assert "No nodes yet" in details.render().plain

        await pilot.press("/")
        for char in "workspace":
            await pilot.press(char)
        await pilot.pause(0.01)

        assert len(tree.root.children) == 0
        assert "No nodes yet" in details.render().plain

        await pilot.press("escape")
        await pilot.pause(0.01)
        assert len(tree.root.children) == 0
        assert "No nodes yet" in details.render().plain


# --- Milestone 0.0.2 PR 4 Interactive Form Dialog Tests ---


@pytest.mark.asyncio
async def test_add_node_dialog_creation_and_cancelling(session: Session) -> None:
    """Test opening the Add Node dialog, typing in values, and cancelling."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger dialog with 'a'
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)

        # Cancel dialog
        await pilot.press("escape")
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_add_node_validation_errors(session: Session) -> None:
    """Test Add Node validation error handling.

    Covers duplicate sibling names and empty names.
    """
    repo = NodeRepository(session)
    repo.create(Node(name="Duplicate Workspace", node_kind="workspace"))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger 'a'
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen

        # Try to submit empty name
        dialog.action_submit()
        await pilot.pause(0.01)
        status_area = dialog.query_one("#status-area")
        assert "Name cannot be empty" in status_area.render().plain

        # Type a duplicate name
        dialog.query_one("#input-name").value = "Duplicate Workspace"
        dialog.query_one("#select-parent").value = None
        dialog.action_submit()
        await pilot.pause(0.01)
        assert "already exists" in status_area.render().plain

        # Change name to valid and click Create
        dialog.query_one("#input-name").value = "Unique Workspace"
        dialog.action_submit()
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"

        tree = app.screen.query_one("#tree-view")
        assert len(tree.root.children) == 2


@pytest.mark.asyncio
async def test_add_node_warning_for_unavailable_path(session: Session) -> None:
    """Test nonblocking warning displays when entering unavailable Directory path."""
    node_service = NodeService(NodeRepository(session))
    # Create a workspace so there's a valid parent
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger 'a'
        await pilot.press("a")
        dialog = app.screen

        # Select Directory type (uses radio set)
        await pilot.click("#radio-directory")
        await pilot.pause(0.01)

        dialog.query_one("#input-name").value = "My Directory"
        dialog.query_one("#input-path").value = "/nonexistent/path/for/warning/test"
        dialog.query_one("#select-parent").value = ws.id
        await pilot.pause(0.05)

        # Warning should be visible
        warning_area = dialog.query_one("#warning-area")
        assert "does not currently exist" in warning_area.render().plain

        # Creation should still succeed
        dialog.action_submit()
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"

        tree = app.screen.query_one("#tree-view")
        assert len(tree.root.children) == 1


@pytest.mark.asyncio
async def test_edit_node_flow(session: Session) -> None:
    """Test Edit Node dialog loading, updating, validations, and promotion."""
    repo = NodeRepository(session)
    original_node = repo.create(
        Node(
            name="Temporary Directory",
            node_kind="resource",
            resource_type="directory",
            path="/tmp/edit-test",
            is_temporary=True,
            description="Edit description",
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger edit dialog 'e'
        await pilot.press("e")
        assert isinstance(app.screen, EditNodeDialog)
        dialog = app.screen

        # Form fields initialized correctly
        assert dialog.query_one("#input-name").value == "Temporary Directory"
        assert dialog.query_one("#input-path").value == "/tmp/edit-test"
        assert dialog.query_one("#checkbox-temporary").value is True

        # Promote temporary directory to permanent
        dialog.query_one("#checkbox-temporary").value = False
        dialog.query_one("#input-name").value = "Permanent Directory"
        dialog.action_submit()
        await pilot.pause(0.01)

        assert app.screen.id == "main-screen"

        # Verify DB and tree are refreshed, and selection is preserved
        updated = node_service.get_node(original_node.id)
        assert updated.is_temporary is False
        assert updated.name == "Permanent Directory"

        tree = app.screen.query_one("#tree-view")
        assert str(tree.cursor_node.label) == "Permanent Directory"


@pytest.mark.asyncio
async def test_move_node_parent_selection_rejection_and_success(
    session: Session,
) -> None:
    """Test Move Node dialog choices, exclusions, and successful parent relocation."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="Workspace One", node_kind="workspace"))
    ws2 = repo.create(Node(name="Workspace Two", node_kind="workspace"))
    res = repo.create(
        Node(
            name="My Resource",
            node_kind="resource",
            resource_type="directory",
            parent_id=ws1.id,
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Select the resource node in the tree (requires expanding ws1 first)
        await pilot.press("l")  # Expand ws1
        await pilot.press("j")  # Go to resource
        assert str(tree.cursor_node.label) == "My Resource"

        # Trigger Move modal with 'm'
        await pilot.press("m")
        assert isinstance(app.screen, MoveNodeDialog)
        dialog = app.screen

        # Choices should include Root and Workspace nodes, excluding resources
        select_widget = dialog.query_one("#select-parent")
        choices = select_widget._options
        # choices are internally represented as tuples: (label, value) or blank
        choice_labels = [str(c[0]) if isinstance(c, tuple) else str(c) for c in choices]
        assert "Root" in choice_labels
        assert "Workspace One" in choice_labels
        assert "Workspace Two" in choice_labels
        assert "My Resource" not in choice_labels

        # Move to Workspace Two
        select_widget.value = ws2.id
        dialog.action_submit()
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"

        # Verify DB and selection
        moved = node_service.get_node(res.id)
        assert moved.parent_id == ws2.id
        assert tree.cursor_node.data == res.id


@pytest.mark.asyncio
async def test_recursive_cascaded_deletion_dialog(session: Session) -> None:
    """Test Delete confirmation dialog.

    Displays correct descendant count and cascades recursively.
    """
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Blender Workspace", node_kind="workspace"))
    repo.create(Node(name="Blender Assets", node_kind="folder", parent_id=ws.id))
    repo.create(Node(name="Blender Config", node_kind="folder", parent_id=ws.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger delete on Blender Workspace
        tree = app.screen.query_one("#tree-view")
        assert str(tree.cursor_node.label) == "Blender Workspace"

        await pilot.press("d")
        assert isinstance(app.screen, ConfirmDeleteDialog)
        dialog = app.screen

        # Should display correct descendant count
        assert dialog.descendant_count == 2
        message_labels = [label.render().plain for label in dialog.query("Label")]
        assert any("delete 2 descendants" in text for text in message_labels)

        # Confirm Deletion using Delete button click/enter
        dialog.query_one("#btn-delete").focus()
        await pilot.press("enter")
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"

        # Verify everything is deleted
        assert len(tree.root.children) == 0
        assert node_service.get_node(ws.id) is None


@pytest.mark.asyncio
async def test_delete_dialog_cancellation_regression(session: Session) -> None:
    """Test focusing Cancel and pressing Enter closes dialog without deletion.

    Ensures no deletion or notification occurs.
    """
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Safe Workspace", node_kind="workspace"))
    child = repo.create(Node(name="Safe Assets", node_kind="folder", parent_id=ws.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("d")
        assert isinstance(app.screen, ConfirmDeleteDialog)
        dialog = app.screen

        # Focus Cancel button and press Enter
        dialog.query_one("#btn-cancel").focus()
        await pilot.press("enter")
        await pilot.pause(0.01)

        # Assert dialog closed
        assert app.screen.id == "main-screen"

        # Assert node and descendant still exist in DB
        assert node_service.get_node(ws.id) is not None
        assert node_service.get_node(child.id) is not None


@pytest.mark.asyncio
async def test_delete_leaf_reports_zero_descendants(session: Session) -> None:
    """Test that deleting a leaf node reports zero descendants in notification."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Leaf Node", node_kind="workspace"))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("d")
        assert isinstance(app.screen, ConfirmDeleteDialog)
        dialog = app.screen
        assert dialog.descendant_count == 0

        # Confirm Deletion
        dialog.query_one("#btn-delete").focus()
        await pilot.press("enter")
        await pilot.pause(0.01)

        assert app.screen.id == "main-screen"
        assert node_service.get_node(ws.id) is None


@pytest.mark.asyncio
async def test_delete_escape_cancellation(session: Session) -> None:
    """Test that pressing Escape closes the Delete dialog without deletion."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Safe Node", node_kind="workspace"))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("d")
        assert isinstance(app.screen, ConfirmDeleteDialog)

        await pilot.press("escape")
        await pilot.pause(0.01)

        assert app.screen.id == "main-screen"
        assert node_service.get_node(ws.id) is not None


@pytest.mark.asyncio
async def test_add_node_dialog_migrated_db_regression(tmp_path: Path) -> None:
    """Async UI regression test using a migrated legacy database.

    Verifies:
    - open AddNodeDialog;
    - create a Workspace;
    - verify the dialog closes cleanly;
    - verify the node appears in the tree;
    - verify no traceback screen appears;
    - cover Folder and Directory creation through the service on this database.
    """
    import sqlite3

    from pathtree.database.connection import create_db_engine, init_db

    db_file = tmp_path / "legacy_ui_regression.db"
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    # Create legacy v1 schema (NOT NULL node_type, no default)
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

    # Run v2 migration
    engine = create_db_engine(db_file)
    init_db(engine)

    with Session(engine) as session:
        repo = NodeRepository(session)
        node_service = NodeService(repo)

        app = PathTreeApp(node_service=node_service)
        async with app.run_test() as pilot:
            while app.screen.id != "main-screen":
                await pilot.pause(0.01)
            await pilot.pause(0.01)

            # 1. Trigger Add Node Dialog
            await pilot.press("a")
            assert isinstance(app.screen, AddNodeDialog)
            dialog = app.screen

            # 2. Enter workspace name
            dialog.query_one("#input-name").value = "Migrated Workspace"

            # 3. Submit/Create (this will insert and verify NO IntegrityError is raised)
            dialog.action_submit()
            await pilot.pause(0.01)

            # 4. Verify the dialog closes cleanly
            assert app.screen.id == "main-screen"

            # 5. Verify the node appears in the tree
            tree = app.screen.query_one("#tree-view")
            assert len(tree.root.children) == 1
            assert str(tree.root.children[0].label) == "Migrated Workspace"

            # 6. Verify no traceback screen appears (app is still on main-screen)
            assert app.screen.id == "main-screen"

        # 7. Also cover Folder and Directory creation via service on migrated db
        ws_node = node_service.load_root_nodes()[0]
        assert ws_node.name == "Migrated Workspace"

        # - Create Folder
        folder = node_service.create_node(
            name="Service Folder", node_kind="folder", parent_id=ws_node.id
        )
        assert folder.id is not None
        assert folder.node_kind == "folder"
        assert folder.legacy_node_type == "Folder"

        # - Create Directory Resource
        res = node_service.create_node(
            name="Service Directory",
            node_kind="resource",
            resource_type="directory",
            parent_id=folder.id,
            path="/tmp/migrated-service-dir",
        )
        assert res.id is not None
        assert res.node_kind == "resource"
        assert res.resource_type == "directory"
        assert res.legacy_node_type == "Folder"

    engine.dispose()


@pytest.mark.asyncio
async def test_add_node_dialog_persistence_failure_display(session: Session) -> None:
    """Verify AddNodeDialog displays a persistence failure cleanly without crash."""
    from unittest import mock

    from pathtree.services.node_service import ValidationError

    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger dialog
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen

        # Type a name
        dialog.query_one("#input-name").value = "Will Fail Node"

        # Mock node_service.create_node to raise ValidationError
        with mock.patch.object(
            node_service,
            "create_node",
            side_effect=ValidationError(
                "Database persistence violated integrity: simulated constraints failed"
            ),
        ):
            dialog.action_submit()
            await pilot.pause(0.01)

            # Dialog must remain open (not dismissed)
            assert isinstance(app.screen, AddNodeDialog)

            # Error message must be displayed in the status-area
            status_area = dialog.query_one("#status-area")
            assert "simulated constraints failed" in status_area.render().plain

            # App didn't crash and no traceback screen is pushed
            assert app.screen == dialog


@pytest.mark.asyncio
async def test_add_dialog_parent_behavior(session: Session) -> None:
    """Verify context-sensitive parent behavior in AddNodeDialog."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Workspace Node", node_kind="workspace"))
    folder = repo.create(Node(name="Folder Node", node_kind="folder", parent_id=ws.id))
    repo.create(
        Node(
            name="Dir Node",
            node_kind="resource",
            resource_type="directory",
            parent_id=folder.id,
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # 1. Open dialog with 'a' while workspace selected
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen

        # Workspace is selected by default -> Parent is hidden/disabled
        select_parent = dialog.query_one("#select-parent")
        assert select_parent.disabled is True
        assert select_parent.value is None or not isinstance(
            select_parent.value, uuid.UUID
        )

        # Submit creates at root
        dialog.query_one("#input-name").value = "WS Two"
        dialog.action_submit()
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"
        assert len(node_service.load_root_nodes()) == 2

        # 2. Open dialog while Folder selected
        # Expand WS Node first
        tree = app.screen.query_one("#tree-view")
        # Move cursor to Workspace Node explicitly
        ws_tree_node = next(
            child
            for child in tree.root.children
            if str(child.label) == "Workspace Node"
        )
        tree.move_cursor(ws_tree_node)
        await pilot.pause(0.01)

        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Go to Folder Node
        assert str(tree.cursor_node.label) == "Folder Node"

        await pilot.press("a")
        dialog = app.screen
        # Switch to Folder Node Type
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)

        # Parent is enabled and has Folder Node as default value
        select_parent = dialog.query_one("#select-parent")
        assert select_parent.disabled is False
        assert select_parent.value == folder.id

        # Verify Directory resource is absent from choices
        choices = select_parent._options
        choice_labels = [str(c[0]) if isinstance(c, tuple) else str(c) for c in choices]
        assert "Dir Node" not in choice_labels

        # Cancel dialog
        await pilot.press("escape")

        # 3. Open dialog while Directory selected -> uses its parent
        # (Folder Node) as default parent.
        await pilot.press("l")  # Expand Folder
        await pilot.press("j")  # Go to Directory Node
        assert str(tree.cursor_node.label) == "Dir Node"

        await pilot.press("a")
        dialog = app.screen
        await pilot.click("#radio-directory")
        await pilot.pause(0.01)

        select_parent = dialog.query_one("#select-parent")
        assert select_parent.value == folder.id

        # Cancel
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_multiple_root_workspaces(session: Session) -> None:
    """Verify separate root workspaces with deterministic order."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="Test", node_kind="workspace", sort_order=1))
    coding = repo.create(Node(name="Coding", node_kind="folder", parent_id=ws1.id))
    repo.create(Node(name="Python", node_kind="folder", parent_id=coding.id))

    ws2 = repo.create(Node(name="Blender", node_kind="workspace", sort_order=2))
    repo.create(Node(name="Assets", node_kind="folder", parent_id=ws2.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        assert len(tree.root.children) == 2

        # Verify Test and Blender are separate root-level nodes in correct order
        assert str(tree.root.children[0].label) == "Test"
        assert str(tree.root.children[1].label) == "Blender"

        # Blender is NOT nested under Test
        assert len(tree.root.children[0].children) == 1
        assert str(tree.root.children[0].children[0].label) == "Coding"


@pytest.mark.asyncio
async def test_expansion_state_preservation(session: Session) -> None:
    """Verify tree expansion state is preserved across CRUD operations."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="Test", node_kind="workspace", sort_order=1))
    coding = repo.create(Node(name="Coding", node_kind="folder", parent_id=ws1.id))
    repo.create(Node(name="Python", node_kind="folder", parent_id=coding.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Expand both WS and Folder
        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Move to coding
        await pilot.press("l")  # Expand Folder
        await pilot.pause(0.01)

        ws_tree_node = tree.root.children[0]
        coding_tree_node = ws_tree_node.children[0]
        assert ws_tree_node.is_expanded is True
        assert coding_tree_node.is_expanded is True

        # Perform Add operation
        await pilot.press("a")
        dialog = app.screen
        dialog.query_one("#input-name").value = "New WS"
        dialog.action_submit()
        await pilot.pause(0.01)

        # Verify expansion remains preserved by finding nodes by label
        ws_tree_node = next(
            child for child in tree.root.children if str(child.label) == "Test"
        )
        coding_tree_node = next(
            child for child in ws_tree_node.children if str(child.label) == "Coding"
        )
        assert ws_tree_node.is_expanded is True
        assert coding_tree_node.is_expanded is True


@pytest.mark.asyncio
async def test_expansion_state_during_search(session: Session) -> None:
    """Verify distinct search-based expansion vs persistent user expansion state."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Workspace Node", node_kind="workspace"))
    folder = repo.create(Node(name="Folder Node", node_kind="folder", parent_id=ws.id))
    repo.create(Node(name="Target Node", node_kind="folder", parent_id=folder.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        ws_tree_node = tree.root.children[0]
        folder_tree_node = ws_tree_node.children[0]

        # Initially, not expanded by the user
        assert ws_tree_node.is_expanded is False
        assert folder_tree_node.is_expanded is False

        # Start search matching 'Target'
        await pilot.press("/")
        for char in "target":
            await pilot.press(char)
        await pilot.pause(0.01)

        # matching expands matching ancestor chains
        ws_tree_node = tree.root.children[0]
        folder_tree_node = ws_tree_node.children[0]
        assert ws_tree_node.is_expanded is True
        assert folder_tree_node.is_expanded is True

        # Clear search restores the pre-search expansion state (False)
        await pilot.press("escape")
        await pilot.pause(0.01)

        ws_tree_node = tree.root.children[0]
        folder_tree_node = ws_tree_node.children[0]
        assert ws_tree_node.is_expanded is False
        assert folder_tree_node.is_expanded is False


def test_resolve_parent_id_sentinels() -> None:
    """Verify resolve_parent_id covers blank sentinels explicitly."""
    from textual.widgets import Select

    from pathtree.ui.dialogs.add_node import resolve_parent_id as add_resolve
    from pathtree.ui.dialogs.move_node import resolve_parent_id as move_resolve

    test_uuid = uuid.uuid4()

    for resolve in (add_resolve, move_resolve):
        assert resolve(Select.BLANK) is None
        assert resolve(Select.NULL) is None
        assert resolve(None) is None
        assert resolve(test_uuid) == test_uuid
        assert resolve("not-a-uuid") is None


@pytest.mark.asyncio
async def test_add_dialog_radio_set_switching(session: Session) -> None:
    """Verify dialog state and default parent restoration when switching."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Workspace Node", node_kind="workspace"))
    folder = repo.create(Node(name="Folder Node", node_kind="folder", parent_id=ws.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        # Expand and navigate to Folder Node
        ws_node = next(
            child
            for child in tree.root.children
            if str(child.label) == "Workspace Node"
        )
        tree.move_cursor(ws_node)
        await pilot.pause(0.01)
        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Go to Folder Node

        # Open add dialog
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen

        # Default Workspace -> parent is hidden and blank
        select_parent = dialog.query_one("#select-parent")
        assert select_parent.disabled is True

        # Switch to Folder Node Type via clicking
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        # Switching Workspace -> Folder restores valid parent options.
        assert select_parent.disabled is False
        assert select_parent.value == folder.id

        # Switch back to Workspace
        await pilot.click("#radio-workspace")
        await pilot.pause(0.01)
        # Switching Folder/Directory -> Workspace clears the previous parent
        assert select_parent.disabled is True
        assert select_parent.value is None or not isinstance(
            select_parent.value, uuid.UUID
        )

        # Cancel
        await pilot.press("escape")
