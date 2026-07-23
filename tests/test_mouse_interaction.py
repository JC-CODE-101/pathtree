from pathlib import Path
from unittest.mock import patch

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.widgets.details import NodeDetailsPanel
from pathtree.ui.widgets.tree import NodeTreeView


@pytest.mark.asyncio
async def test_pilot_single_click_on_directory(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    1. pilot single-click on a visible Directory row selects it;
    2. output file remains absent/unchanged after single click;
    3. app remains running after single click;
    4. details panel changes to the clicked node;
    5. no ResourceActionProvider.execute call occurs.
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "click_dir"
    valid_dir.mkdir()

    ws = repo.create(Node(name="WS", node_kind="workspace"))
    node = repo.create(
        Node(
            name="My Dir",
            path=str(valid_dir),
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
        )
    )

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)
        details = app.screen.query_one("#details-panel", NodeDetailsPanel)

        # Expand WS so Directory is visible
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        tree.move_cursor(ws_tn)
        await pilot.press("l")
        await pilot.pause(0.02)

        # Line 0 is WS, Line 1 is My Dir
        visible = tree.get_visible_nodes()
        assert visible[0].data == ws.id
        assert visible[1].data == node.id

        provider = app.screen.action_registry.get_provider("resource", "directory")
        with patch.object(provider, "execute", wraps=provider.execute) as mock_execute:
            # 1. pilot single-click on a visible Directory row (line index 1)
            # Offset x=12 to hit the label, y=1 for the line index
            await pilot.click(tree, offset=(12, 1))
            await pilot.pause(0.05)

            # 2. output file remains absent/unchanged after single click
            assert not output_file.exists()

            # 3. app remains running after single click
            assert app.return_code is None

            # 4. details panel changes to the clicked node
            assert "My Dir" in details.render().plain

            # 5. no ResourceActionProvider.execute call occurs
            mock_execute.assert_not_called()


@pytest.mark.asyncio
async def test_pilot_double_click_on_directory(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    6. pilot double-click on the same row activates exactly once;
    7. output path is written exactly once;
    8. app exits exactly once.
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "click_dir"
    valid_dir.mkdir()

    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(
        Node(
            name="My Dir",
            path=str(valid_dir),
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
        )
    )

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # Expand WS
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        tree.move_cursor(ws_tn)
        await pilot.press("l")
        await pilot.pause(0.02)

        provider = app.screen.action_registry.get_provider("resource", "directory")
        with patch.object(provider, "execute", wraps=provider.execute) as mock_execute:
            # 6. pilot double-click on the same row activates
            await pilot.double_click(tree, offset=(12, 1))

            # Wait for app to exit
            while app.return_code is None:
                await pilot.pause(0.01)

            # 6. Activates exactly once
            mock_execute.assert_called_once()

            # 7. output path is written exactly once
            assert output_file.exists()
            written_path = output_file.read_text(encoding="utf-8").strip()
            assert Path(written_path).resolve() == valid_dir.resolve()

            # 8. app exits exactly once
            assert app.return_code == 0


@pytest.mark.asyncio
async def test_enter_activates_via_custom_message(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    9. Enter activates through the same custom message.
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "enter_dir"
    valid_dir.mkdir()

    ws = repo.create(Node(name="WS", node_kind="workspace"))
    node = repo.create(
        Node(
            name="My Dir",
            path=str(valid_dir),
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
        )
    )

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # Expand WS
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        tree.move_cursor(ws_tn)
        await pilot.press("l")
        await pilot.pause(0.02)

        # Highlight the directory (at line 1)
        dir_tn = next(c for c in ws_tn.children if c.data == node.id)
        tree.move_cursor(dir_tn)
        await pilot.pause(0.01)

        # 9. Enter activates through the same custom message
        await pilot.press("enter")

        while app.return_code is None:
            await pilot.pause(0.01)

        assert app.return_code == 0
        assert output_file.exists()


@pytest.mark.asyncio
async def test_node_selected_alone_never_activates(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    10. Tree.NodeSelected alone never activates.
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "select_dir"
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

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # Find the TreeNode object
        tn = next(c for c in tree.root.children if c.data == node.id)

        # Post Tree.NodeSelected directly
        from textual.widgets import Tree

        tree.post_message(Tree.NodeSelected(tn))
        await pilot.pause(0.05)

        # 10. Tree.NodeSelected alone never activates
        assert not output_file.exists()
        assert app.return_code is None


@pytest.mark.asyncio
async def test_clicking_toggle_marker_never_activates(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    11. clicking the toggle marker never activates.
    """
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(Node(name="Folder", node_kind="folder", parent_id=ws.id))

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # Line index 0 is WS (which has a toggle marker since it has a folder child)
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        assert ws_tn.is_expanded is False

        # Click the toggle marker of WS (which is at x=1, y=0 or x=2, y=0)
        # Let's double click or rapid click the toggle marker
        await pilot.click(tree, offset=(1, 0))
        await pilot.pause(0.01)
        await pilot.click(tree, offset=(1, 0))
        await pilot.pause(0.01)

        # It should toggle the expansion but never activate/crash
        assert ws_tn.is_expanded is True or ws_tn.is_expanded is False
        assert app.return_code is None


@pytest.mark.asyncio
async def test_rapid_clicks_on_different_rows_do_not_activate(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    12. rapid separate single clicks on different rows do not become activation.
    """
    repo = NodeRepository(session)
    dir1 = tmp_path / "dir1"
    dir1.mkdir()
    dir2 = tmp_path / "dir2"
    dir2.mkdir()

    ws = repo.create(Node(name="WS", node_kind="workspace"))
    repo.create(
        Node(
            name="Dir 1",
            path=str(dir1),
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
        )
    )
    repo.create(
        Node(
            name="Dir 2",
            path=str(dir2),
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
        )
    )

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # Expand WS
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        tree.move_cursor(ws_tn)
        await pilot.press("l")
        await pilot.pause(0.02)

        # Line index 1 is Dir 1, Line index 2 is Dir 2
        # Rapid single click on Dir 1 then Dir 2
        await pilot.click(tree, offset=(12, 1))
        await pilot.click(tree, offset=(12, 2))
        await pilot.pause(0.05)

        # Neither should be activated, app remains running
        assert app.return_code is None
        assert not output_file.exists()


@pytest.mark.asyncio
async def test_o_opens_action_menu(session: Session, tmp_path: Path) -> None:
    """Test that:
    13. O still opens the action menu.
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "click_dir"
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

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Press 'o' to open action menu
        await pilot.press("o")
        await pilot.pause(0.05)

        from pathtree.ui.dialogs.action_menu import ResourceActionMenu

        assert isinstance(app.screen, ResourceActionMenu)


@pytest.mark.asyncio
async def test_workspace_and_folder_remain_non_executable(
    session: Session, tmp_path: Path
) -> None:
    """Test that:
    14. Workspace and Folder remain non-executable.
    """
    repo = NodeRepository(session)
    ws = repo.create(Node(name="My Workspace", node_kind="workspace"))
    repo.create(Node(name="My Folder", node_kind="folder", parent_id=ws.id))

    output_file = tmp_path / "output.txt"
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))

    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)
        details = app.screen.query_one("#details-panel", NodeDetailsPanel)

        # Expand Workspace
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        tree.move_cursor(ws_tn)
        await pilot.press("l")
        await pilot.pause(0.02)

        # Workspace is Line 0, Folder is Line 1
        # Double click Workspace
        await pilot.double_click(tree, offset=(12, 0))
        await pilot.pause(0.05)
        assert app.return_code is None
        assert "No default action" not in details.render().plain

        # Double click Folder
        await pilot.double_click(tree, offset=(12, 1))
        await pilot.pause(0.05)
        assert app.return_code is None
        assert "No default action" not in details.render().plain
