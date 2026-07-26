"""Tests for the Resource Action Menu TUI integration."""

from pathlib import Path

import pytest
from sqlmodel import Session
from textual.app import App

from pathtree.actions.base import ResourceAction
from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.action_menu import ActionMenuItem, ResourceActionMenu


@pytest.mark.asyncio
async def test_action_menu_opening_for_dir_res(
    session: Session, tmp_path: Path
) -> None:
    """Verify pressing 'O' opens the action menu for a Directory resource."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    res = repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        # Let's expand workspace to make child visible
        await pilot.press("l")
        await pilot.pause(0.05)
        # Select child
        await pilot.press("j")
        await pilot.pause(0.05)

        assert tree.cursor_node is not None
        assert tree.cursor_node.data == res.id

        # Press O to open the action menu
        await pilot.press("O")
        await pilot.pause(0.05)

        assert isinstance(app.screen, ResourceActionMenu)
        assert app.screen.title_text == "Actions for My Dir"

        # Check menu entries are correct
        menu_items = list(app.screen.query(ActionMenuItem))
        assert len(menu_items) == 4
        labels = [item.action.label for item in menu_items]
        assert "Change Directory" in labels
        assert "Copy Path" in labels
        assert "View Details" in labels
        assert "Pin Node" in labels or "Unpin Node" in labels

        # Escape closes the menu
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_action_menu_default_marked(session: Session, tmp_path: Path) -> None:
    """Verify that default action in the Action Menu is visibly marked."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        await pilot.press("l")
        await pilot.press("j")
        await pilot.press("O")
        await pilot.pause(0.05)

        assert isinstance(app.screen, ResourceActionMenu)
        menu_items = list(app.screen.query(ActionMenuItem))
        # The first item is default and should have is_default
        default_item = next(item for item in menu_items if item.action.is_default)
        assert default_item.action.id == "change_directory"
        assert "* Change Directory" in default_item.render()


@pytest.mark.asyncio
async def test_action_menu_nav_wrapping(session: Session, tmp_path: Path) -> None:
    """Verify keyboard navigation (j/k, up/down, Ctrl+J/Ctrl+K) wraps."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        await pilot.press("l")
        await pilot.press("j")
        await pilot.press("O")
        await pilot.pause(0.05)

        assert isinstance(app.screen, ResourceActionMenu)
        menu = app.screen
        assert menu.highlighted_index == 0  # Starts at 0

        # Down/j/Ctrl+J goes to next
        await pilot.press("j")
        assert menu.highlighted_index == 1
        await pilot.press("down")
        assert menu.highlighted_index == 2
        await pilot.press("ctrl+j")
        assert menu.highlighted_index == 3
        await pilot.press("j")
        assert menu.highlighted_index == 0  # Wraps to 0

        # Up/k/Ctrl+K goes to previous
        await pilot.press("k")
        assert menu.highlighted_index == 3  # Wraps to last (3)
        await pilot.press("up")
        assert menu.highlighted_index == 2
        await pilot.press("ctrl+k")
        assert menu.highlighted_index == 1

        await pilot.press("escape")


@pytest.mark.asyncio
async def test_action_menu_enter_executes_action(
    session: Session, tmp_path: Path
) -> None:
    """Verify pressing Enter on highlighted enabled action executes it."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        await pilot.press("l")
        await pilot.press("j")
        await pilot.press("O")
        await pilot.pause(0.05)

        # Highlight "Copy Path" (index 1)
        await pilot.press("j")
        await pilot.press("enter")
        await pilot.pause(0.05)

        # It should execute copy_path and display path in details
        assert app.screen.id == "main-screen"
        details = app.screen.query_one("#details-panel")
        assert f"Path: {tmp_path!s}" in details.render().plain


@pytest.mark.asyncio
async def test_action_menu_escape_closes(session: Session, tmp_path: Path) -> None:
    """Verify Escape closes the menu and tree selection remains unchanged."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    res = repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        await pilot.press("l")
        await pilot.press("j")
        await pilot.press("O")
        await pilot.pause(0.05)

        await pilot.press("escape")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == res.id


@pytest.mark.asyncio
async def test_all_nodes_can_open_menu_to_pin_unpin(session: Session) -> None:
    """Verify Workspace/Folder can open the menu for Pinning/Unpinning."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(Node(name="Folder 1", node_kind="folder", parent_id=ws.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # 1. Workspace selected (WS)
        await pilot.press("O")
        await pilot.pause(0.05)
        assert isinstance(app.screen, ResourceActionMenu)
        menu_items = list(app.screen.query(ActionMenuItem))
        assert len(menu_items) == 1
        assert menu_items[0].action.id == "pin_node"

        await pilot.press("escape")
        await pilot.pause(0.05)

        # 2. Folder selected
        await pilot.press("l")
        await pilot.press("j")
        await pilot.pause(0.05)
        await pilot.press("O")
        await pilot.pause(0.05)
        assert isinstance(app.screen, ResourceActionMenu)
        menu_items = list(app.screen.query(ActionMenuItem))
        assert len(menu_items) == 1
        assert menu_items[0].action.id == "pin_node"


@pytest.mark.asyncio
async def test_copy_path_and_view_details_behavior(
    session: Session, tmp_path: Path
) -> None:
    """Verify copy_path displays path and view_details updates panel."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
            description="Detailed directory description",
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        await pilot.press("l")
        await pilot.press("j")

        # 1. View Details
        await pilot.press("O")
        await pilot.pause(0.05)
        await pilot.press("j")
        await pilot.press("j")  # Highlight View Details (index 2)
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        details = app.screen.query_one("#details-panel")
        assert "Detailed directory description" in details.render().plain

        # 2. Copy Path
        await pilot.press("O")
        await pilot.pause(0.05)
        await pilot.press("j")  # Highlight Copy Path (index 1)
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        assert f"Path: {tmp_path!s}" in details.render().plain


@pytest.mark.asyncio
async def test_mainscreen_execute_action_generic_behavior(
    session: Session, tmp_path: Path
) -> None:
    """Verify that MainScreen has no action-ID specific branching."""
    import inspect

    from pathtree.actions.base import (
        ResourceAction,
        ResourceActionResult,
        ResourceActionResultTarget,
    )
    from pathtree.ui.screens.main import MainScreen

    # 1. Assert no concrete action-ID string checks exist in MainScreen.execute_action
    source = inspect.getsource(MainScreen.execute_action)
    assert "change_directory" not in source
    assert "copy_path" not in source
    assert "view_details" not in source

    # 2. Assert a future/custom action ID executes flawlessly
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # Mock the provider to return a future action dynamically
        provider = app.screen.action_registry.get_provider("resource", "directory")
        original_get_actions = provider.get_available_actions
        original_execute = provider.execute

        custom_action = ResourceAction(
            id="future_custom_act", label="Future Action", is_enabled=True
        )

        def mock_get_actions(ctx):
            return [custom_action]

        def mock_execute(action_id, ctx):
            if action_id == "future_custom_act":
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    output_value="Custom generic result content!",
                    target=ResourceActionResultTarget.DETAILS,
                )
            return original_execute(action_id, ctx)

        provider.get_available_actions = mock_get_actions
        provider.execute = mock_execute

        try:
            await pilot.press("l")
            await pilot.press("j")
            await pilot.press("O")
            await pilot.pause(0.05)

            # Hit enter on our future custom action
            await pilot.press("enter")
            await pilot.pause(0.05)

            details = app.screen.query_one("#details-panel")
            assert "Custom generic result content!" in details.render().plain
        finally:
            provider.get_available_actions = original_get_actions
            provider.execute = original_execute


@pytest.mark.asyncio
async def test_disabled_actions_do_not_execute() -> None:
    """Verify that disabled actions cannot be executed."""
    # Create actions list containing a disabled action
    actions = [
        ResourceAction(id="enabled_act", label="Enabled Action", is_enabled=True),
        ResourceAction(id="disabled_act", label="Disabled Action", is_enabled=False),
    ]
    menu = ResourceActionMenu(actions)

    # Run test on the ResourceActionMenu modal
    class MockApp(App[None]):
        def compose(self):
            yield from []

    app = MockApp()
    async with app.run_test() as pilot:
        # Push screen
        await app.push_screen(menu)
        await pilot.pause(0.05)

        # Highlight index 1 (disabled action)
        await pilot.press("j")
        # Try to execute by pressing enter
        await pilot.press("enter")
        await pilot.pause(0.05)

        # It should NOT dismiss/close the menu since it's disabled
        assert app.screen is menu

        # Escape closes it
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_change_directory_output_behavior(
    session: Session, tmp_path: Path
) -> None:
    """Verify change_directory preserves output file behavior & state."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )

    output_file = tmp_path / "out.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        await pilot.press("l")
        await pilot.press("j")
        await pilot.press("O")
        await pilot.pause(0.05)

        # Change Directory is index 0, so just press enter
        await pilot.press("enter")
        await pilot.pause(0.05)

        # It should exit the app when result.exit_app is true
        # App should be closed / pilot finished
        # We can verify output_file has the resolved path
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == str(tmp_path)
