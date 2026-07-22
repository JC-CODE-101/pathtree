"""TUI layout, navigation, and interactive management tests."""

import uuid
from pathlib import Path

import pytest
from sqlmodel import Session
from textual.app import App, ComposeResult

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.dialogs.confirm_delete import ConfirmDeleteDialog
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.dialogs.move_node import MoveNodeDialog
from pathtree.ui.widgets.path_autocomplete import PathAutocomplete


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

        # Choices should include Workspace nodes, excluding Root and resources
        select_widget = dialog.query_one("#select-parent")
        choices = select_widget._options
        # choices are internally represented as tuples: (label, value) or blank
        choice_labels = [str(c[0]) if isinstance(c, tuple) else str(c) for c in choices]
        assert "Root" not in choice_labels
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
    async with app.run_test(size=(80, 60)) as pilot:
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


class KeyboardShortcutTestApp(App[None]):
    """Test app with PathAutocomplete and a subsequent Input widget."""

    def compose(self) -> ComposeResult:
        from textual.widgets import Input

        yield PathAutocomplete(id="input-path")
        yield Input(id="input-description")


@pytest.mark.asyncio
async def test_path_autocomplete_recursive_symlink_prevention(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify recursive symlinks are excluded from candidates to prevent loops."""
    root = tmp_path / "root"
    root.mkdir()
    code = root / "code"
    code.mkdir()

    # Create symlink cycle: root/code/cycle -> root/code
    cycle_link = code / "cycle"
    try:
        cycle_link.symlink_to(code, target_is_directory=True)
    except OSError:
        pass

    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        # Go inside root/code/cycle/
        input_widget.value = "root/code/cycle/"
        await pilot.pause(0.05)

        # The option list should not contain "cycle/" because root/code/cycle
        # resolves to root/code, which is already in the ancestor chain.
        # It should show "No matching directories." because there are no other folders.
        assert widget.option_list.option_count == 1
        assert (
            str(widget.option_list.get_option_at_index(0).prompt)
            == "No matching directories."
        )


@pytest.mark.asyncio
async def test_path_autocomplete_no_match_behavior(tmp_path: Path, monkeypatch) -> None:
    """Verify no-match state clears stale options, shows error.

    Blocks Tab/Enter path changes.
    """
    root = tmp_path / "root"
    root.mkdir()

    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        # Type a prefix with no match
        input_widget.value = "root/nonexistent"
        await pilot.pause(0.05)

        # Suggestions should be visible showing "No matching directories."
        assert widget.is_suggestions_visible is True
        assert widget.option_list.option_count == 1
        assert (
            str(widget.option_list.get_option_at_index(0).prompt)
            == "No matching directories."
        )

        # Press Tab
        await pilot.press("tab")
        await pilot.pause(0.01)
        # Value must remain unchanged
        assert input_widget.value == "root/nonexistent"

        # Refocus/retype
        input_widget.focus()
        input_widget.value = "root/nonexistent"
        await pilot.pause(0.05)

        # Press Enter
        await pilot.press("enter")
        await pilot.pause(0.01)
        # Value must remain unchanged and suggestion popups are hidden
        assert input_widget.value == "root/nonexistent"
        assert widget.is_suggestions_visible is False


@pytest.mark.asyncio
async def test_path_autocomplete_shift_enter_behavior(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify Shift+Enter hides suggestions and shifts focus without submitting."""
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)

    app = KeyboardShortcutTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        input_widget.value = "su"
        await pilot.pause(0.05)
        assert widget.is_suggestions_visible is True

        # Press Shift+Enter
        await pilot.press("shift+enter")
        await pilot.pause(0.01)

        # Suggestions hidden, path unchanged, focus moves to description field
        assert widget.is_suggestions_visible is False
        assert input_widget.value == "su"
        assert app.focused.id == "input-description"


@pytest.mark.asyncio
async def test_path_autocomplete_shift_space_behavior(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify Shift+Space reopens suggestions without inserting a space."""
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        input_widget.value = "su"
        await pilot.pause(0.05)
        assert widget.is_suggestions_visible is True

        # Hide first
        await pilot.press("escape")
        await pilot.pause(0.01)
        assert widget.is_suggestions_visible is False

        # Press Shift+Space to reopen
        await pilot.press("shift+space")
        await pilot.pause(0.05)

        # Reopened, path unchanged (no space inserted), suggestions visible
        assert widget.is_suggestions_visible is True
        assert input_widget.value == "su"
        assert widget.option_list.option_count == 1
        assert str(widget.option_list.get_option_at_index(0).prompt) == "sub/"


@pytest.mark.asyncio
async def test_path_autocomplete_chained_tab_completion(
    tmp_path: Path, monkeypatch
) -> None:
    """Test chained Tab completion through multiple directory levels."""
    import os

    # Structure: root/code/python/projects/
    root = tmp_path / "root"
    code = root / "code"
    python = code / "python"
    projects = python / "projects"
    projects.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        # 1. Type partial
        input_widget.value = "root/co"
        await pilot.pause(0.05)

        assert widget.is_suggestions_visible is True
        option_list = widget.option_list
        assert option_list.option_count == 1
        assert str(option_list.get_option_at_index(0).prompt) == "code/"

        # 2. Press Tab -> completes to root/code/
        # and immediately opens children of code/
        await pilot.press("tab")
        await pilot.pause(0.05)

        assert input_widget.value == "root/code/"
        assert widget.is_suggestions_visible is True
        assert option_list.option_count == 1
        assert str(option_list.get_option_at_index(0).prompt) == "python/"
        assert option_list.highlighted == 0
        assert app.focused is input_widget

        # 3. Press Tab -> completes to root/code/python/ and immediately opens children
        await pilot.press("tab")
        await pilot.pause(0.05)

        assert input_widget.value == "root/code/python/"
        assert widget.is_suggestions_visible is True
        assert option_list.option_count == 1
        assert str(option_list.get_option_at_index(0).prompt) == "projects/"
        assert option_list.highlighted == 0

        # 4. Press Tab -> completes to root/code/python/projects/
        # Since projects/ has no children, it should show "No matching directories."
        await pilot.press("tab")
        await pilot.pause(0.05)

        assert input_widget.value == "root/code/python/projects/"
        assert widget.is_suggestions_visible is True
        assert option_list.option_count == 1
        assert option_list.get_option_at_index(0).disabled is True
        assert "No matching directories" in str(
            option_list.get_option_at_index(0).prompt
        )


@pytest.mark.asyncio
async def test_path_autocomplete_chained_enter_completion(
    tmp_path: Path, monkeypatch
) -> None:
    """Test that Enter closes suggestions without accepting or modifying the path."""
    root = tmp_path / "root"
    code = root / "code"
    python = code / "python"
    python.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        input_widget.value = "root/co"
        await pilot.pause(0.05)

        assert widget.is_suggestions_visible is True

        # First Enter closes suggestions without accepting
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert input_widget.value == "root/co"
        assert widget.is_suggestions_visible is False


@pytest.mark.asyncio
async def test_path_autocomplete_empty_accepted_directory(
    tmp_path: Path, monkeypatch
) -> None:
    """Test empty match state and no stale suggestions upon directory acceptance."""
    root = tmp_path / "root"
    root.mkdir()  # empty!

    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        input_widget.value = "r"
        await pilot.pause(0.05)
        assert widget.is_suggestions_visible is True
        assert str(widget.option_list.get_option_at_index(0).prompt) == "root/"

        # Accept
        await pilot.press("tab")
        await pilot.pause(0.05)

        # Output should be "No matching directories."
        # and no stale suggestions from the parent
        assert input_widget.value == "root/"
        assert widget.is_suggestions_visible is True
        assert widget.option_list.option_count == 1
        assert widget.option_list.get_option_at_index(0).disabled is True
        assert "No matching directories" in str(
            widget.option_list.get_option_at_index(0).prompt
        )


@pytest.mark.asyncio
async def test_path_autocomplete_editing_after_acceptance(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify editing/backspacing after acceptance immediately refreshes suggestions."""
    root = tmp_path / "root"
    code = root / "code"
    python = code / "python"
    python.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        input_widget.value = "root/co"
        await pilot.pause(0.05)

        # Accept
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_widget.value == "root/code/"
        assert widget.option_list.option_count == 1

        # Press backspace (input value becomes "root/code")
        await pilot.press("backspace")
        await pilot.pause(0.05)

        # It should immediately rescan the parent directory and find "code/"
        # because value is "root/code"
        assert input_widget.value == "root/code"
        assert widget.is_suggestions_visible is True
        assert str(widget.option_list.get_option_at_index(0).prompt) == "code/"


@pytest.mark.asyncio
async def test_path_autocomplete_tilde_relative_absolute_chained(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify tilde, relative, and absolute chained completion."""
    import os

    root = tmp_path / "root"
    code = root / "code"
    code.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        # 1. Tilde
        input_widget.value = "~/r"
        await pilot.pause(0.05)
        assert widget.is_suggestions_visible is True
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_widget.value == "~/root/"
        assert str(widget.option_list.get_option_at_index(0).prompt) == "code/"

        # 2. Relative
        input_widget.value = "./r"
        await pilot.pause(0.05)
        assert widget.is_suggestions_visible is True
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_widget.value == "./root/"
        assert str(widget.option_list.get_option_at_index(0).prompt) == "code/"

        # 3. Absolute
        input_widget.value = str(tmp_path) + "/r"
        await pilot.pause(0.05)
        assert widget.is_suggestions_visible is True
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_widget.value == str(tmp_path) + "/root/"
        assert str(widget.option_list.get_option_at_index(0).prompt) == "code/"


def get_screen_y(widget) -> int:
    """Helper to calculate the absolute screen Y coordinate of a widget."""
    y = 0
    curr = widget
    while curr is not None and curr != curr.screen:
        y += curr.region.y
        curr = curr.parent
    return y


@pytest.mark.asyncio
async def test_add_node_dialog_autocomplete_overlay_properties(
    session: Session, tmp_path: Path
) -> None:
    """Rigorous rendering and layering test for PathAutocomplete in AddNodeDialog."""
    node_service = NodeService(NodeRepository(session))
    node_service.create_node(name="WS", node_kind="workspace")
    (tmp_path / "blocks").mkdir()

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger dialog
        await pilot.press("a")
        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)

        await pilot.click("#radio-directory")
        await pilot.pause(0.01)

        p_widget = dialog.query_one("#input-path-wrapper", PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Type partial path
        input_path.value = str(tmp_path) + "/b"
        await pilot.pause(0.05)

        # Locate OptionList
        option_list = p_widget.option_list
        assert option_list.display is True
        assert option_list.visible is True
        assert option_list.region.width > 0
        assert option_list.region.height > 0
        assert option_list.is_on_screen is True

        # Assert overlay layer
        assert option_list.styles.layer == "overlay"

        # Assert region.y begins below the Path input (using screen-relative Y)
        assert option_list.region.y >= input_path.region.bottom

        # Verify vertical overlap: OptionList's y range overlaps description field
        desc_container = dialog.query_one("#input-description").parent
        description_label = desc_container.query_one("Label")
        assert option_list.region.y <= description_label.region.y + 2
        assert option_list.region.bottom > description_label.region.y + 1

        # Assert Path input retains focus
        assert app.focused is input_path

        # Navigate suggestions list
        assert option_list.highlighted == 0
        await pilot.press("down")
        await pilot.pause(0.01)
        assert option_list.highlighted == 0  # only 1 match (blocks/)

        # Accept visible option
        await pilot.press("tab")
        await pilot.pause(0.05)
        # Slices to empty match state on the newly accepted blocks/
        assert p_widget.is_suggestions_visible is True
        assert "No matching directories" in str(
            p_widget.option_list.get_option_at_index(0).prompt
        )
        assert input_path.value == str(tmp_path) + "/blocks/"


@pytest.mark.asyncio
async def test_edit_node_dialog_autocomplete_overlay_properties(
    session: Session, tmp_path: Path
) -> None:
    """Rigorous rendering and layering test for PathAutocomplete in EditNodeDialog."""
    node_service = NodeService(NodeRepository(session))
    ws = node_service.create_node(name="WS", node_kind="workspace")
    (tmp_path / "blocks").mkdir()

    node_service.create_node(
        name="Edit Node",
        node_kind="resource",
        resource_type="directory",
        parent_id=ws.id,
        path=str(tmp_path),
    )

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        app.screen.query_one("#tree-view")
        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Move to child node

        # Trigger edit modal
        await pilot.press("e")
        dialog = app.screen
        assert isinstance(dialog, EditNodeDialog)

        p_widget = dialog.query_one("#input-path-wrapper", PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Change path to trigger suggestions
        input_path.value = str(tmp_path) + "/b"
        await pilot.pause(0.05)

        # Locate OptionList
        option_list = p_widget.option_list
        assert option_list.display is True
        assert option_list.visible is True
        assert option_list.region.width > 0
        assert option_list.region.height > 0
        assert option_list.is_on_screen is True

        # Assert overlay layer
        assert option_list.styles.layer == "overlay"

        # Assert region.y begins below the Path input (using screen-relative Y)
        assert option_list.region.y >= input_path.region.bottom

        # Assert vertical overlap: OptionList overlaps with following fields
        desc_container = dialog.query_one("#input-description").parent
        description_label = desc_container.query_one("Label")
        assert option_list.region.y <= description_label.region.y + 2
        assert option_list.region.bottom > description_label.region.y + 1

        # Assert Path input retains focus
        assert app.focused is input_path

        # Accept visible option
        await pilot.press("tab")
        await pilot.pause(0.05)
        # Slices to empty match state on the newly accepted blocks/
        assert p_widget.is_suggestions_visible is True
        assert "No matching directories" in str(
            p_widget.option_list.get_option_at_index(0).prompt
        )
        assert input_path.value == str(tmp_path) + "/blocks/"


@pytest.mark.asyncio
async def test_add_node_dialog_visibility_regression(session: Session) -> None:
    """Verify PathAutocomplete visibility, dimensions, focus, and rendering order."""
    from pathtree.ui.widgets.path_autocomplete import PathAutocompleteInput

    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # 1. Trigger dialog
        await pilot.press("a")
        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)

        path_container = dialog.query_one("#path-field-container")
        autocomplete = dialog.query_one("#input-path-wrapper", PathAutocomplete)
        inner_input = autocomplete.query_one(
            ".path-autocomplete-input", PathAutocompleteInput
        )
        path_label = dialog.query_one("#path-field-container Label")
        description_label = dialog.query_one("#input-description").parent.query_one(
            "Label"
        )

        # Initially Workspace -> hidden
        assert path_container.display is False

        # Helper to assert that inner input is fully rendered, visible,
        # sized, and on-screen
        async def assert_input_fully_rendered():
            await pilot.pause(0.05)  # wait for layout refresh
            assert inner_input.visible is True
            assert inner_input.display is True
            assert inner_input.region.width > 0
            assert inner_input.region.height >= 3
            assert inner_input.is_on_screen is True

            # Assert vertical layout rendering order
            assert path_label.region.y < inner_input.region.y
            assert inner_input.region.bottom <= description_label.region.y

        # --- Test 1: Workspace -> Directory ---
        await pilot.click("#radio-directory")
        await assert_input_fully_rendered()

        # Verify focus and interactive typing
        inner_input.focus()
        await pilot.pause(0.01)
        assert app.focused is inner_input

        # Type text
        await pilot.press("tilde", "slash", "w", "s")
        await pilot.pause(0.01)
        assert inner_input.value == "~/ws"

        # --- Test 2: Directory -> Folder ---
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        assert path_container.display is False

        # --- Test 3: Folder -> Directory ---
        await pilot.click("#radio-directory")
        await assert_input_fully_rendered()

        # Verify focus and typing again
        inner_input.focus()
        await pilot.pause(0.01)
        assert app.focused is inner_input

        # Clear and type again
        inner_input.value = ""
        await pilot.press("tilde", "slash", "w", "s")
        await pilot.pause(0.01)
        assert inner_input.value == "~/ws"

        # --- Test 4: Directory -> Folder -> Directory ---
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        assert path_container.display is False

        await pilot.click("#radio-directory")
        await assert_input_fully_rendered()

        await pilot.press("escape")
        if app.screen.id != "main-screen":
            await pilot.press("escape")


class AutocompleteTestApp(App[None]):
    """Simple test app to isolate PathAutocomplete testing."""

    def compose(self) -> ComposeResult:
        yield PathAutocomplete(id="input-path")


class DualAutocompleteApp(App[None]):
    """Simple test app with two PathAutocomplete widgets."""

    def compose(self) -> ComposeResult:
        yield PathAutocomplete(id="path1")
        yield PathAutocomplete(id="path2")


@pytest.mark.asyncio
async def test_path_autocomplete_basic_typing(tmp_path: Path, monkeypatch) -> None:
    """Test that typing generates sorted directory suggestions only."""

    (tmp_path / "blocks").mkdir()
    (tmp_path / "blender").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "some_file.txt").touch()  # Files should not be suggested

    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        await pilot.press("b")
        await pilot.press("l")
        await pilot.pause(0.01)

        assert widget.is_suggestions_visible is True
        option_list = widget.option_list
        assert option_list.option_count == 2
        assert str(option_list.get_option_at_index(0).prompt) == "blender/"
        assert str(option_list.get_option_at_index(1).prompt) == "blocks/"


@pytest.mark.asyncio
async def test_path_autocomplete_navigation_keys(tmp_path: Path, monkeypatch) -> None:
    """Test navigation with Up/Down and Ctrl+n/Ctrl+p inside PathAutocomplete."""
    from textual.events import Key

    (tmp_path / "blocks").mkdir()
    (tmp_path / "blender").mkdir()

    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        input_widget.value = "b"
        await pilot.pause(0.01)

        option_list = widget.option_list
        assert option_list.highlighted == 0

        # Ctrl+n
        await pilot.press("ctrl+n")
        assert option_list.highlighted == 1

        # Ctrl+p
        input_widget.post_message(Key("ctrl+p", None))
        await pilot.pause(0.01)
        assert option_list.highlighted == 0

        # Down
        await pilot.press("down")
        assert option_list.highlighted == 1

        # Up
        await pilot.press("up")
        assert option_list.highlighted == 0


@pytest.mark.asyncio
async def test_path_autocomplete_relative_absolute_and_tilde(
    tmp_path: Path, monkeypatch
) -> None:
    """Test relative, absolute, and tilde expansions inside PathAutocomplete."""
    import os

    (tmp_path / "blender").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        # 1. Relative dot path
        input_widget.value = "./b"
        await pilot.pause(0.01)
        option_list = widget.option_list
        assert str(option_list.get_option_at_index(0).prompt) == "blender/"
        await pilot.press("tab")
        await pilot.pause(0.01)
        assert input_widget.value == "./blender/"

        # 2. Absolute path
        input_widget.value = str(tmp_path) + "/b"
        await pilot.pause(0.01)
        assert str(option_list.get_option_at_index(0).prompt) == "blender/"
        await pilot.press("tab")
        await pilot.pause(0.01)
        assert input_widget.value == str(tmp_path) + "/blender/"

        # 3. Tilde path
        input_widget.value = "~/b"
        await pilot.pause(0.01)
        assert str(option_list.get_option_at_index(0).prompt) == "blender/"
        await pilot.press("tab")
        await pilot.pause(0.01)
        assert input_widget.value == "~/blender/"


@pytest.mark.asyncio
async def test_path_autocomplete_validation_states(tmp_path: Path, monkeypatch) -> None:
    """Test empty matches and nonexistent directory validation states."""

    monkeypatch.chdir(tmp_path)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        widget = app.screen.query_one(PathAutocomplete)
        input_widget = widget.query_one("#input-path")
        input_widget.focus()
        await pilot.pause(0.01)

        # 1. No matches
        input_widget.value = "xyz"
        await pilot.pause(0.01)
        option_list = widget.option_list
        assert option_list.option_count == 1
        assert option_list.get_option_at_index(0).disabled is True
        assert "No matching directories" in str(
            option_list.get_option_at_index(0).prompt
        )

        # 2. Nonexistent parent directory
        input_widget.value = "nonexistent/b"
        await pilot.pause(0.01)
        assert option_list.option_count == 1
        assert option_list.get_option_at_index(0).disabled is True
        assert "Directory does not exist" in str(
            option_list.get_option_at_index(0).prompt
        )


@pytest.mark.asyncio
async def test_dual_path_autocomplete(tmp_path: Path, monkeypatch) -> None:
    """Verify multiple PathAutocomplete widgets on one screen operate independently."""
    (tmp_path / "blocks").mkdir()
    (tmp_path / "blender").mkdir()
    (tmp_path / "other").mkdir()

    monkeypatch.chdir(tmp_path)

    app = DualAutocompleteApp()
    async with app.run_test() as pilot:
        p1 = app.screen.query_one("#path1-wrapper", PathAutocomplete)
        p2 = app.screen.query_one("#path2-wrapper", PathAutocomplete)

        input1 = p1.query_one("#path1")
        input1.focus()
        await pilot.press("b")
        await pilot.pause(0.01)

        # Widget 1 shows suggestions, Widget 2 is hidden
        assert p1.is_suggestions_visible is True
        assert p2.is_suggestions_visible is False

        # Widget 2 gains focus and typed into
        input2 = p2.query_one("#path2")
        input2.focus()
        await pilot.press("o")
        await pilot.pause(0.01)

        # Widget 1 is hidden because it lost focus/blurred, Widget 2 is visible
        assert p1.is_suggestions_visible is False
        assert p2.is_suggestions_visible is True


@pytest.mark.asyncio
async def test_add_node_dialog_autocomplete_enter_acceptance_and_creation(
    session: Session, tmp_path: Path
) -> None:
    """Test Enter accepts autocomplete suggestions before dialog submit."""
    node_service = NodeService(NodeRepository(session))
    ws = node_service.create_node(name="WS", node_kind="workspace")

    (tmp_path / "suggested_folder").mkdir()

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("a")
        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)

        await pilot.click("#radio-directory")
        await pilot.pause(0.01)

        dialog.query_one("#input-name").value = "New Directory Node"
        dialog.query_one("#select-parent").value = ws.id

        p_widget = dialog.query_one("#input-path-wrapper", PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Input partially matching
        input_path.value = str(tmp_path) + "/s"
        await pilot.pause(0.01)
        assert p_widget.is_suggestions_visible is True

        # First Tab: accepts suggestion, immediately reopens with empty state
        # (No matching directories)
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        assert "No matching directories" in str(
            p_widget.option_list.get_option_at_index(0).prompt
        )
        assert input_path.value == str(tmp_path) + "/suggested_folder/"
        assert isinstance(app.screen, AddNodeDialog)

        # Second Enter: closes suggestions
        await pilot.press("enter")
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is False

        # Third Enter: submits and creates
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        from sqlmodel import select

        assert len(session.exec(select(Node)).all()) == 2


@pytest.mark.asyncio
async def test_edit_node_dialog_autocomplete(session: Session, tmp_path: Path) -> None:
    """Test EditNodeDialog properly loads and supports autocomplete changes."""
    node_service = NodeService(NodeRepository(session))
    ws = node_service.create_node(name="WS", node_kind="workspace")

    orig_dir = tmp_path / "orig_dir"
    orig_dir.mkdir()
    new_dir = tmp_path / "new_dir"
    new_dir.mkdir()

    node = node_service.create_node(
        name="Edit Node",
        node_kind="resource",
        resource_type="directory",
        parent_id=ws.id,
        path=str(orig_dir),
    )

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        app.screen.query_one("#tree-view")
        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Move to child node

        # Trigger edit modal
        await pilot.press("e")
        dialog = app.screen
        assert isinstance(dialog, EditNodeDialog)

        p_widget = dialog.query_one("#input-path-wrapper", PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        assert input_path.value == str(orig_dir)

        # Change path to trigger autocomplete
        input_path.focus()
        input_path.value = str(tmp_path) + "/n"
        await pilot.pause(0.01)
        assert p_widget.is_suggestions_visible is True

        # Accept new path
        await pilot.press("tab")
        await pilot.pause(0.01)
        assert input_path.value == str(tmp_path) + "/new_dir/"

        # Save and close
        dialog.action_submit()
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"

        updated = node_service.get_node(node.id)
        assert updated.path == str(tmp_path) + "/new_dir"


@pytest.mark.asyncio
async def test_add_node_dialog_escape_closes_suggestions_first(
    session: Session,
) -> None:
    """Verify Escape closes suggestions popup first, and second Escape closes dialog."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        await pilot.press("a")
        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)

        await pilot.click("#radio-directory")
        await pilot.pause(0.01)

        p_widget = dialog.query_one("#input-path-wrapper", PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        input_path.value = "."
        await pilot.pause(0.01)
        assert p_widget.is_suggestions_visible is True

        # First Escape: suggestions closed, dialog stays
        await pilot.press("escape")
        await pilot.pause(0.01)
        assert p_widget.is_suggestions_visible is False
        assert isinstance(app.screen, AddNodeDialog)

        # Second Escape: dialog closed
        await pilot.press("escape")
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_path_autocomplete_spaces(tmp_path: Path) -> None:
    """Test autocomplete works seamlessly with directories containing spaces."""
    (tmp_path / "folder with spaces").mkdir()

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        input_path.value = str(tmp_path) + "/folder"
        await pilot.pause(0.01)
        assert p_widget.is_suggestions_visible is True

        await pilot.press("tab")
        await pilot.pause(0.01)
        assert input_path.value == str(tmp_path) + "/folder with spaces/"


@pytest.mark.asyncio
async def test_path_autocomplete_permission_denied(tmp_path: Path, monkeypatch) -> None:
    """Verify permission denied filesystem error outputs correctly."""
    import os

    def mock_scandir(path):
        raise PermissionError("Permission denied.")

    monkeypatch.setattr(os, "scandir", mock_scandir)

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        input_path.value = str(tmp_path) + "/b"
        await pilot.pause(0.01)

        assert p_widget.is_suggestions_visible is True
        option_list = p_widget.option_list
        assert option_list.option_count == 1
        assert option_list.get_option_at_index(0).disabled is True
        assert str(option_list.get_option_at_index(0).prompt) == "Permission denied."


@pytest.mark.asyncio
async def test_path_autocomplete_click_option(tmp_path: Path) -> None:
    """Verify OptionSelected event directly maps and accepts the clicked Option."""
    from textual.widgets import OptionList

    (tmp_path / "blocks").mkdir()
    (tmp_path / "blender").mkdir()

    app = AutocompleteTestApp()
    async with app.run_test() as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        input_path.value = str(tmp_path) + "/b"
        await pilot.pause(0.01)
        assert p_widget.is_suggestions_visible is True

        option_list = p_widget.option_list
        # Select second option specifically to bypass highlighted mismatch
        option_list.highlighted = 0
        target_option = option_list.get_option_at_index(1)  # blocks/

        # Post OptionSelected manually
        option_list.post_message(
            OptionList.OptionSelected(option_list, target_option, 1)
        )
        await pilot.pause(0.05)

        assert p_widget.is_suggestions_visible is True
        assert "No matching directories" in str(
            p_widget.option_list.get_option_at_index(0).prompt
        )
        assert input_path.value == str(tmp_path) + "/blocks/"


def test_no_debug_output_in_path_autocomplete() -> None:
    """Ensure no print() debug statement is used in the PathAutocomplete widget."""
    from pathlib import Path

    path_file = Path("src/pathtree/ui/widgets/path_autocomplete.py")
    content = path_file.read_text(encoding="utf-8")
    assert "print(" not in content, (
        "PathAutocomplete should not contain print statements!"
    )


@pytest.mark.asyncio
async def test_add_node_dialog_vim_navigation(session: Session) -> None:
    """Test Vim-style navigation (j/k) and standard arrow key
    navigation in AddNodeDialog.

    Ensures:
    - 'j' moves Workspace -> Folder -> Directory
    - 'k' moves Directory -> Folder -> Workspace
    - Arrow keys still work (e.g. right/left)
    - j/k typed inside Name, Path, Description, or Icon inputs remain normal text
    - selected_type stays synchronized with the active RadioButton
    """
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # 1. Trigger dialog
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen

        # Node type starts as "workspace"
        assert dialog.selected_type == "workspace"

        # Focus the RadioSet to test j/k
        radio_set = dialog.query_one("#node-type-radio-set")
        radio_set.focus()
        await pilot.pause(0.01)
        assert app.focused == radio_set

        # Test 'j' moves Workspace -> Folder
        await pilot.press("j")
        await pilot.pause(0.01)
        assert dialog.selected_type == "folder"

        # Test 'j' moves Folder -> Directory
        await pilot.press("j")
        await pilot.pause(0.01)
        assert dialog.selected_type == "directory"

        # Test wrapping with 'j' moves Directory -> Workspace
        await pilot.press("j")
        await pilot.pause(0.01)
        assert dialog.selected_type == "workspace"

        # Test 'k' moves Workspace -> Directory (wrapping)
        await pilot.press("k")
        await pilot.pause(0.01)
        assert dialog.selected_type == "directory"

        # Test 'k' moves Directory -> Folder
        await pilot.press("k")
        await pilot.pause(0.01)
        assert dialog.selected_type == "folder"

        # Test 'k' moves Folder -> Workspace
        await pilot.press("k")
        await pilot.pause(0.01)
        assert dialog.selected_type == "workspace"

        # Test arrow keys still work
        # Move to Folder using arrow key (e.g. right) and toggle/press it with Space
        await pilot.press("right")
        await pilot.pause(0.01)
        await pilot.press("space")
        await pilot.pause(0.01)
        assert dialog.selected_type == "folder"

        # 2. Test j/k typed inside input fields remain normal text and do not navigate
        input_name = dialog.query_one("#input-name")
        input_name.focus()
        await pilot.pause(0.01)
        assert app.focused == input_name

        # Type "j" and "k"
        await pilot.press("j")
        await pilot.press("k")
        await pilot.pause(0.01)

        # Check input value has "jk"
        assert input_name.value == "jk"
        # Node Type remains Folder (was not changed by typing j/k in Input)
        assert dialog.selected_type == "folder"

        # Test description input
        input_desc = dialog.query_one("#input-description")
        input_desc.focus()
        await pilot.pause(0.01)
        await pilot.press("j")
        await pilot.pause(0.01)
        assert input_desc.value == "j"
        assert dialog.selected_type == "folder"

        # Test icon input (always visible)
        input_icon = dialog.query_one("#input-icon")
        input_icon.focus()
        await pilot.pause(0.01)
        await pilot.press("k")
        await pilot.pause(0.01)
        assert input_icon.value == "k"
        assert dialog.selected_type == "folder"

        # Switch to directory type so path input is visible/displayed
        radio_set.focus()
        await pilot.pause(0.01)
        await pilot.press("j")  # moves folder -> directory
        await pilot.pause(0.01)
        assert dialog.selected_type == "directory"

        # Test path input (now visible)
        input_path = dialog.query_one("#input-path")
        input_path.focus()
        await pilot.pause(0.01)
        await pilot.press("j")
        await pilot.press("k")
        await pilot.pause(0.01)
        assert input_path.value == "jk"
        assert dialog.selected_type == "directory"

        # Cancel dialog
        await pilot.press("escape")
        await pilot.pause(0.01)
        if app.screen.id != "main-screen":
            await pilot.press("escape")
            await pilot.pause(0.01)
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_add_and_move_blank_selection_constraints(session: Session) -> None:
    """Verify select validation and blank selection constraints in dialogs."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Workspace One", node_kind="workspace"))
    folder = repo.create(Node(name="Folder One", node_kind="folder", parent_id=ws.id))
    repo.create(
        Node(
            name="Dir One",
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

        tree = app.screen.query_one("#tree-view")

        # Navigate to Workspace Node to start
        ws_node = next(
            child for child in tree.root.children if str(child.label) == "Workspace One"
        )
        tree.move_cursor(ws_node)
        await pilot.pause(0.01)

        # 1. Folder Add Select always has a valid UUID parent selected
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)

        select_parent = dialog.query_one("#select-parent")
        assert isinstance(select_parent.value, uuid.UUID)
        await pilot.press("escape")

        # 2. Directory Add Select always has a valid UUID parent selected
        await pilot.press("a")
        dialog = app.screen
        await pilot.click("#radio-directory")
        await pilot.pause(0.01)

        select_parent = dialog.query_one("#select-parent")
        assert isinstance(select_parent.value, uuid.UUID)
        await pilot.press("escape")

        # Navigate to Folder Node
        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Move to Folder One
        assert str(tree.cursor_node.label) == "Folder One"

        # 3. Folder Move Select always has a valid UUID parent selected
        await pilot.press("m")
        assert isinstance(app.screen, MoveNodeDialog)
        move_dialog = app.screen
        select_parent_move = move_dialog.query_one("#select-parent")
        assert isinstance(select_parent_move.value, uuid.UUID)
        await pilot.press("escape")

        # Navigate to Dir Node
        await pilot.press("l")  # Expand Folder
        await pilot.press("j")  # Move to Dir One
        assert str(tree.cursor_node.label) == "Dir One"

        # 4. Directory Move Select always has a valid UUID parent selected
        await pilot.press("m")
        assert isinstance(app.screen, MoveNodeDialog)
        move_dialog = app.screen
        select_parent_move = move_dialog.query_one("#select-parent")
        assert isinstance(select_parent_move.value, uuid.UUID)
        await pilot.press("escape")

        # Navigate back to Workspace One
        tree.move_cursor(ws_node)
        await pilot.pause(0.01)

        # 5. Workspace Move still resolves Root to parent_id=None
        await pilot.press("m")
        assert isinstance(app.screen, MoveNodeDialog)
        move_dialog = app.screen
        select_parent_move = move_dialog.query_one("#select-parent")
        # Submit to resolve to None safely
        move_dialog.action_submit()
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_no_valid_add_parent_disables_or_blocks_creation(
    session: Session,
) -> None:
    """Verify that when no valid parent exists, create button is disabled."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # 1. Open add node dialog
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen

        # Switch to Folder Node Type (no workspaces exist in DB)
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)

        select_parent = dialog.query_one("#select-parent")
        create_btn = dialog.query_one("#btn-create")

        # Both Select and Create Button must be disabled
        assert select_parent.disabled is True
        assert create_btn.disabled is True

        await pilot.press("escape")


def test_sentinel_compatibility_scenarios(monkeypatch) -> None:
    """Verify resolve_optional_uuid with simulated configurations."""
    import pathtree.ui.compat as compat

    missing = compat._MISSING
    test_uuid = uuid.uuid4()

    dummy_blank = object()
    dummy_null = object()

    # Scenario 1: Both BLANK and NULL available
    monkeypatch.setattr(compat, "SELECT_BLANK", dummy_blank)
    monkeypatch.setattr(compat, "SELECT_NULL", dummy_null)
    assert compat.resolve_optional_uuid(dummy_blank) is None
    assert compat.resolve_optional_uuid(dummy_null) is None
    assert compat.resolve_optional_uuid(test_uuid) == test_uuid
    assert compat.resolve_optional_uuid(None) is None
    assert compat.resolve_optional_uuid("unknown") is None

    # Scenario 2: Only NULL available
    monkeypatch.setattr(compat, "SELECT_BLANK", missing)
    monkeypatch.setattr(compat, "SELECT_NULL", dummy_null)
    assert compat.resolve_optional_uuid(dummy_blank) is None  # falls through
    assert compat.resolve_optional_uuid(dummy_null) is None
    assert compat.resolve_optional_uuid(test_uuid) == test_uuid

    # Scenario 3: Only BLANK available
    monkeypatch.setattr(compat, "SELECT_BLANK", dummy_blank)
    monkeypatch.setattr(compat, "SELECT_NULL", missing)
    assert compat.resolve_optional_uuid(dummy_blank) is None
    assert compat.resolve_optional_uuid(dummy_null) is None  # falls through
    assert compat.resolve_optional_uuid(test_uuid) == test_uuid


@pytest.mark.asyncio
async def test_expansion_state_preservation_detailed(session: Session) -> None:
    """Verify detailed tree expansion state preservation."""
    repo = NodeRepository(session)
    # Duplicate labels "Coding" in different branches to verify restore by UUID
    ws1 = repo.create(Node(name="WS1", node_kind="workspace", sort_order=1))
    coding1 = repo.create(Node(name="Coding", node_kind="folder", parent_id=ws1.id))
    repo.create(Node(name="Python1", node_kind="folder", parent_id=coding1.id))
    # OtherFolder under WS1 to ensure WS1 remains non-empty after Coding is moved
    repo.create(Node(name="OtherFolder", node_kind="folder", parent_id=ws1.id))

    ws2 = repo.create(Node(name="WS2", node_kind="workspace", sort_order=2))
    coding2 = repo.create(Node(name="Coding", node_kind="folder", parent_id=ws2.id))
    repo.create(Node(name="Python2", node_kind="folder", parent_id=coding2.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Expand WS1 -> Coding, leaving WS2 -> Coding collapsed
        # Find WS1 node in tree
        ws1_tn = next(child for child in tree.root.children if child.data == ws1.id)
        tree.move_cursor(ws1_tn)
        await pilot.pause(0.01)
        await pilot.press("l")  # Expand WS1
        await pilot.press("j")  # Move to first Coding
        await pilot.press("l")  # Expand Coding 1
        await pilot.pause(0.01)

        ws1_tn = next(child for child in tree.root.children if child.data == ws1.id)
        coding1_tn = ws1_tn.children[0]
        assert ws1_tn.is_expanded is True
        assert coding1_tn.is_expanded is True

        ws2_tn = next(child for child in tree.root.children if child.data == ws2.id)
        assert ws2_tn.is_expanded is False

        # --- 1. Expanded branches remain expanded after Edit ---
        await pilot.press("e")  # Edit Coding 1
        dialog = app.screen
        dialog.query_one("#input-name").value = "Coding Edited"
        dialog.action_submit()
        await pilot.pause(0.01)

        ws1_tn = next(child for child in tree.root.children if child.data == ws1.id)
        coding1_tn = ws1_tn.children[0]
        assert ws1_tn.is_expanded is True
        assert coding1_tn.is_expanded is True
        assert str(coding1_tn.label) == "Coding Edited"

        # --- 2. Expanded unrelated Workspace remains expanded after Move ---
        # WS2 (collapsed) will be moved or ws1 (expanded) remains expanded
        # Let's add a folder to WS2, expand WS2, then move coding1 to WS2
        # WS1 remains expanded
        node_service.move_node(coding1.id, ws2.id)
        app.screen.refresh_tree(selected_node_id=coding1.id)
        await pilot.pause(0.01)

        ws1_tn = next(child for child in tree.root.children if child.data == ws1.id)
        assert ws1_tn.is_expanded is True  # WS1 remains expanded

        # --- 3. Expanded parent remains expanded after deleting a child ---
        # Expand WS2
        ws2_tn = next(child for child in tree.root.children if child.data == ws2.id)
        tree.move_cursor(ws2_tn)
        await pilot.pause(0.01)
        await pilot.press("l")  # Expand WS2
        await pilot.pause(0.01)

        ws2_tn = next(child for child in tree.root.children if child.data == ws2.id)
        assert ws2_tn.is_expanded is True

        # Delete one of WS2's children
        child_to_delete = ws2_tn.children[1]  # coding2
        node_service.delete_node(child_to_delete.data, recursive=True)
        app.screen.refresh_tree()
        await pilot.pause(0.01)

        ws2_tn = next(child for child in tree.root.children if child.data == ws2.id)
        assert (
            ws2_tn.is_expanded is True
        )  # Parent WS2 remains expanded after deleting a child


@pytest.mark.asyncio
async def test_search_mutation_query_preservation(session: Session) -> None:
    """Verify mutation during active search preserves the query."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Workspace Node", node_kind="workspace"))
    folder = repo.create(Node(name="Target Node", node_kind="folder", parent_id=ws.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Start search matching 'Target'
        await pilot.press("/")
        for char in "target":
            await pilot.press(char)
        await pilot.pause(0.01)

        search_input = app.screen.query_one("#search-input")
        assert search_input.value == "target"

        # Mutate the node (edit it)
        node_service.update_node(folder.id, name="Target Node Edited")
        app.screen.refresh_tree(selected_node_id=folder.id)
        await pilot.pause(0.01)

        # Search query is preserved
        assert search_input.value == "target"


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
    """Verify resolve_optional_uuid covers blank sentinels explicitly."""
    from textual.widgets import Select

    from pathtree.ui.compat import resolve_optional_uuid

    test_uuid = uuid.uuid4()

    sel_blank = getattr(Select, "BLANK", None)
    sel_null = getattr(Select, "NULL", None)

    if sel_blank is not None:
        assert resolve_optional_uuid(sel_blank) is None
    if sel_null is not None:
        assert resolve_optional_uuid(sel_null) is None
    assert resolve_optional_uuid(None) is None
    assert resolve_optional_uuid(test_uuid) == test_uuid
    assert resolve_optional_uuid("not-a-uuid") is None


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
        assert select_parent.disabled is True

        # Cancel
        await pilot.press("escape")
