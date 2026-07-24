"""Unit and integration tests for Workspace visual spacing in NodeTreeView."""

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.widgets.tree import NodeTreeView


@pytest.mark.asyncio
async def test_workspace_spacing_rendering(session: Session) -> None:
    """Test tree rendering and spacing modes with multiple workspaces."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="WS1", node_kind="workspace"))
    ws2 = repo.create(Node(name="WS2", node_kind="workspace"))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one(NodeTreeView)

        # 1. Compact spacing (0 spacer lines)
        tree.spacing_mode = "compact"
        await pilot.pause(0.01)
        lines = tree._tree_lines
        assert len(lines) == 2
        assert lines[0].node.data == ws1.id
        assert getattr(lines[0], "is_spacer", False) is False
        assert lines[1].node.data == ws2.id
        assert getattr(lines[1], "is_spacer", False) is False

        # 2. Normal spacing (1 spacer line)
        tree.spacing_mode = "normal"
        await pilot.pause(0.01)
        lines = tree._tree_lines
        assert len(lines) == 3
        assert lines[0].node.data == ws1.id
        assert getattr(lines[0], "is_spacer", False) is False
        assert getattr(lines[1], "is_spacer", False) is True
        assert lines[2].node.data == ws2.id
        assert getattr(lines[2], "is_spacer", False) is False

        # 3. Wide spacing (2 spacer lines)
        tree.spacing_mode = "wide"
        await pilot.pause(0.01)
        lines = tree._tree_lines
        assert len(lines) == 4
        assert lines[0].node.data == ws1.id
        assert getattr(lines[0], "is_spacer", False) is False
        assert getattr(lines[1], "is_spacer", False) is True
        assert getattr(lines[2], "is_spacer", False) is True
        assert lines[3].node.data == ws2.id
        assert getattr(lines[3], "is_spacer", False) is False


@pytest.mark.asyncio
async def test_workspace_spacing_keyboard_navigation(session: Session) -> None:
    """Test that keyboard navigation completely skips spacer lines."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="WS1", node_kind="workspace"))
    ws2 = repo.create(Node(name="WS2", node_kind="workspace"))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one(NodeTreeView)
        tree.spacing_mode = "normal"
        await pilot.pause(0.01)

        tree.cursor_line = 0
        assert tree.cursor_node.data == ws1.id

        await pilot.press("down")
        await pilot.pause(0.01)
        assert tree.cursor_line == 2
        assert tree.cursor_node.data == ws2.id

        await pilot.press("up")
        await pilot.pause(0.01)
        assert tree.cursor_line == 0
        assert tree.cursor_node.data == ws1.id


@pytest.mark.asyncio
async def test_workspace_spacing_mouse_click_ignored(session: Session) -> None:
    """Test that mouse clicks on spacer lines are completely ignored."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="WS1", node_kind="workspace"))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one(NodeTreeView)
        tree.spacing_mode = "normal"
        await pilot.pause(0.01)

        tree.cursor_line = 0
        assert tree.cursor_node.data == ws1.id

        from rich.style import Style
        from textual.events import Click

        event = Click(
            widget=tree,
            x=0,
            y=1,
            delta_x=0,
            delta_y=0,
            button=1,
            shift=False,
            meta=False,
            ctrl=False,
            style=Style.from_meta({"line": 1}),
        )

        tree.post_message(event)
        await pilot.pause(0.01)

        assert tree.cursor_line == 0
        assert tree.cursor_node.data == ws1.id


def test_workspace_spacing_textual_compatibility(session: Session) -> None:
    """Test that all private Textual tree members needed for spacing are available."""
    node_service = NodeService(NodeRepository(session))

    # 1. Verify we can import _TreeLine
    from textual.widgets._tree import _TreeLine

    assert _TreeLine is not None

    # 2. Verify tree has required private methods and attributes
    tree = NodeTreeView(node_service=node_service)
    assert hasattr(tree, "_tree_lines_cached")
    assert hasattr(tree, "_build")
    assert hasattr(tree, "_render_line")
    assert hasattr(tree, "_tree_lines")
