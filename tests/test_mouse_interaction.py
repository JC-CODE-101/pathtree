from pathlib import Path

import pytest
from rich.style import Style
from sqlmodel import Session
from textual.events import Click

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.widgets.details import NodeDetailsPanel
from pathtree.ui.widgets.tree import NodeTreeView


@pytest.mark.asyncio
async def test_single_click_directory(session: Session, tmp_path: Path) -> None:
    """Test that:
    1. single click on a Directory selects it but does not execute;
    2. single click does not write the output file;
    3. single click does not exit the app;
    4. single click updates the details panel;
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "click_dir"
    valid_dir.mkdir()
    node = repo.create(
        Node(
            name="My Dir",
            path=str(valid_dir),
            node_kind="resource",
            resource_type="directory",
        )
    )

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)
        details = app.screen.query_one("#details-panel", NodeDetailsPanel)

        # Find the node's line
        visible = tree.get_visible_nodes()
        line_idx = next(i for i, n in enumerate(visible) if n.data == node.id)

        # Simulate single click
        style = Style(meta={"line": line_idx})
        click_event = Click(
            widget=tree,
            x=0,
            y=0,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            style=style,
            chain=1,
        )
        await tree._on_click(click_event)
        await pilot.pause(0.05)

        # 1. Single click selects the node
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == node.id

        # 2. Does not execute / does not write output file
        assert not output_file.exists()

        # 3. Does not exit the app
        assert app.return_code is None

        # 4. Updates the details panel
        assert "My Dir" in details.render().plain
        assert str(valid_dir) in details.render().plain


@pytest.mark.asyncio
async def test_double_click_directory(session: Session, tmp_path: Path) -> None:
    """Test that:
    5. double click executes the same default action as Enter;
    6. double click writes the resolved Directory path once;
    7. double click exits once on successful change_directory;
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "double_click_dir"
    valid_dir.mkdir()
    node = repo.create(
        Node(
            name="My Dir",
            path=str(valid_dir),
            node_kind="resource",
            resource_type="directory",
        )
    )

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        visible = tree.get_visible_nodes()
        line_idx = next(i for i, n in enumerate(visible) if n.data == node.id)

        # Simulate double click (firing first click then second click)
        style = Style(meta={"line": line_idx})
        click1 = Click(
            widget=tree,
            x=0,
            y=0,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            style=style,
            chain=1,
        )
        await tree._on_click(click1)
        await pilot.pause(0.01)

        click2 = Click(
            widget=tree,
            x=0,
            y=0,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            style=style,
            chain=2,
        )
        await tree._on_click(click2)

        # Wait for the app to exit on successful activation
        while app.return_code is None:
            await pilot.pause(0.01)

        # 5. Executes and exits successfully
        assert app.return_code == 0

        # 6. Writes output file
        assert output_file.exists()
        written_path = output_file.read_text(encoding="utf-8").strip()
        assert Path(written_path).resolve() == valid_dir.resolve()


@pytest.mark.asyncio
async def test_workspace_and_folder_clicks(session: Session, tmp_path: Path) -> None:
    """Test that:
    8. Workspace and Folder single clicks remain selection-only and
       double clicks do not execute them.
    """
    repo = NodeRepository(session)
    ws = repo.create(Node(name="My Workspace", node_kind="workspace"))
    folder = repo.create(Node(name="My Folder", node_kind="folder", parent_id=ws.id))

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)
        details = app.screen.query_one("#details-panel", NodeDetailsPanel)

        # Let's expand the workspace so the folder is visible
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        tree.move_cursor(ws_tn)
        await pilot.press("l")
        await pilot.pause(0.02)

        # Check Workspace single click
        visible = tree.get_visible_nodes()
        ws_idx = next(i for i, n in enumerate(visible) if n.data == ws.id)

        # Click WS
        click_ws = Click(
            widget=tree,
            x=0,
            y=0,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            style=Style(meta={"line": ws_idx}),
            chain=1,
        )
        await tree._on_click(click_ws)
        await pilot.pause(0.01)
        assert tree.cursor_node is not None and tree.cursor_node.data == ws.id
        assert "My Workspace" in details.render().plain

        # Double click WS
        dbl_click_ws = Click(
            widget=tree,
            x=0,
            y=0,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            style=Style(meta={"line": ws_idx}),
            chain=2,
        )
        await tree._on_click(dbl_click_ws)
        await pilot.pause(0.05)
        # Verify no execution, no exit, no error message like "No default action"
        assert app.return_code is None
        assert "No default action" not in details.render().plain

        # Check Folder single click
        folder_idx = next(i for i, n in enumerate(visible) if n.data == folder.id)
        click_folder = Click(
            widget=tree,
            x=0,
            y=0,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            style=Style(meta={"line": folder_idx}),
            chain=1,
        )
        await tree._on_click(click_folder)
        await pilot.pause(0.01)
        assert tree.cursor_node is not None and tree.cursor_node.data == folder.id
        assert "My Folder" in details.render().plain

        # Double click Folder
        dbl_click_folder = Click(
            widget=tree,
            x=0,
            y=0,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            style=Style(meta={"line": folder_idx}),
            chain=2,
        )
        await tree._on_click(dbl_click_folder)
        await pilot.pause(0.05)
        assert app.return_code is None
        assert "No default action" not in details.render().plain


@pytest.mark.asyncio
async def test_unsupported_resource_double_click(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    9. unsupported resources do not crash on double click;
       double click should fail safely using the existing unsupported-action message.
    """
    repo = NodeRepository(session)
    node = repo.create(
        Node(
            name="Unknown Resource",
            node_kind="resource",
            resource_type="unknown_or_invalid",
        )
    )

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)
        details = app.screen.query_one("#details-panel", NodeDetailsPanel)

        visible = tree.get_visible_nodes()
        line_idx = next(i for i, n in enumerate(visible) if n.data == node.id)

        # Single click first
        await tree._on_click(
            Click(
                widget=tree,
                x=0,
                y=0,
                delta_x=0,
                delta_y=0,
                button=1,
                shift=False,
                meta=False,
                ctrl=False,
                style=Style(meta={"line": line_idx}),
                chain=1,
            )
        )
        await pilot.pause(0.01)

        # Double click
        await tree._on_click(
            Click(
                widget=tree,
                x=0,
                y=0,
                delta_x=0,
                delta_y=0,
                button=1,
                shift=False,
                meta=False,
                ctrl=False,
                style=Style(meta={"line": line_idx}),
                chain=2,
            )
        )
        await pilot.pause(0.05)

        # Check that it did not crash, return_code is None
        assert app.return_code is None
        # Check that it failed safely displaying the existing
        # unsupported-action error message
        assert "No default action is available" in details.render().plain


@pytest.mark.asyncio
async def test_keyboard_enter_and_o_remain_unchanged(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    10. keyboard Enter and O behavior remains unchanged.
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "kbd_dir"
    valid_dir.mkdir()
    repo.create(
        Node(
            name="My Dir",
            path=str(valid_dir),
            node_kind="resource",
            resource_type="directory",
        )
    )

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        app.screen.query_one("#tree-view", NodeTreeView)

        # Verify O key opens the resource action menu
        await pilot.press("o")
        await pilot.pause(0.05)

        # Should open the ResourceActionMenu modal screen
        from pathtree.ui.dialogs.action_menu import ResourceActionMenu

        assert isinstance(app.screen, ResourceActionMenu)

        # Close the modal
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.screen.id == "main-screen"

        # Verify Enter key activates/exits
        await pilot.press("enter")
        while app.return_code is None:
            await pilot.pause(0.01)

        assert app.return_code == 0
        assert output_file.exists()


@pytest.mark.asyncio
async def test_tree_state_and_selection_correct_after_click(session: Session) -> None:
    """Test that:
    11. tree state and current selection remain correct.
    """
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="WS 1", node_kind="workspace"))
    ws2 = repo.create(Node(name="WS 2", node_kind="workspace"))
    folder = repo.create(Node(name="Folder", node_kind="folder", parent_id=ws1.id))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # Expand WS 1
        ws1_tn = next(c for c in tree.root.children if c.data == ws1.id)
        tree.move_cursor(ws1_tn)
        await pilot.press("l")
        await pilot.pause(0.01)
        assert ws1_tn.is_expanded is True

        # Now get visible nodes
        visible = tree.get_visible_nodes()
        # Elements are: ws1, folder, ws2
        assert [n.data for n in visible] == [ws1.id, folder.id, ws2.id]

        # Single click on WS 2
        ws2_idx = next(i for i, n in enumerate(visible) if n.data == ws2.id)
        await tree._on_click(
            Click(
                widget=tree,
                x=0,
                y=0,
                delta_x=0,
                delta_y=0,
                button=1,
                shift=False,
                meta=False,
                ctrl=False,
                style=Style(meta={"line": ws2_idx}),
                chain=1,
            )
        )
        await pilot.pause(0.01)

        # Selection should change to WS 2
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == ws2.id

        # WS 1 should remain expanded
        ws1_tn = next(c for c in tree.root.children if c.data == ws1.id)
        assert ws1_tn.is_expanded is True
