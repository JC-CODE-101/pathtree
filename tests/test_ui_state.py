"""Tests for persistent UI tree state restoration and safety."""

import uuid
from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.state import TreeState, TreeStateStore


@pytest.mark.asyncio
async def test_restore_expanded_and_selected(session: Session, tmp_path: Path) -> None:
    """1. Test that expanded nodes and selection are restored on restart."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS1", node_kind="workspace"))
    folder = repo.create(Node(name="F1", node_kind="folder", parent_id=ws.id))
    leaf = repo.create(
        Node(
            name="L1",
            node_kind="resource",
            resource_type="directory",
            parent_id=folder.id,
        )
    )

    state_file = tmp_path / "test-state.json"
    state_store = TreeStateStore(state_file)

    # Pre-populate state
    state = TreeState(expanded_node_ids={ws.id, folder.id}, selected_node_id=leaf.id)
    state_store.save(state)

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, state_store=state_store)

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Verify ws and folder are expanded
        ws_node = next(child for child in tree.root.children if child.data == ws.id)
        assert ws_node.is_expanded is True

        folder_node = next(
            child for child in ws_node.children if child.data == folder.id
        )
        assert folder_node.is_expanded is True

        # Verify cursor is on leaf
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == leaf.id


@pytest.mark.asyncio
async def test_ignore_missing_expanded_node_ids(
    session: Session, tmp_path: Path
) -> None:
    """3. Test that missing/deleted expanded node IDs are ignored safely."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS1", node_kind="workspace"))
    # Add a folder so WS1 is expandable
    repo.create(Node(name="F1", node_kind="folder", parent_id=ws.id))

    state_file = tmp_path / "test-state.json"
    state_store = TreeStateStore(state_file)

    # Pre-populate state with some non-existent UUIDs
    fake_uuid_1 = uuid.uuid4()
    fake_uuid_2 = uuid.uuid4()
    state = TreeState(
        expanded_node_ids={ws.id, fake_uuid_1, fake_uuid_2},
        selected_node_id=ws.id,
    )
    state_store.save(state)

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, state_store=state_store)

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # WS1 is expanded
        ws_node = next(child for child in tree.root.children if child.data == ws.id)
        assert ws_node.is_expanded is True


@pytest.mark.asyncio
async def test_deleted_selected_node_fallback(session: Session, tmp_path: Path) -> None:
    """4. Test that a deleted/missing selected node falls back safely."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="WS1", node_kind="workspace", sort_order=1))
    repo.create(Node(name="WS2", node_kind="workspace", sort_order=2))

    state_file = tmp_path / "test-state.json"
    state_store = TreeStateStore(state_file)

    fake_uuid = uuid.uuid4()
    state = TreeState(expanded_node_ids=set(), selected_node_id=fake_uuid)
    state_store.save(state)

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, state_store=state_store)

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Falls back to normal default selection (WS1)
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == ws1.id


@pytest.mark.asyncio
async def test_malformed_state_file(session: Session, tmp_path: Path) -> None:
    """5. Test that malformed/corrupted state data does not prevent startup."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="WS1", node_kind="workspace"))

    state_file = tmp_path / "test-state.json"
    # Write garbage content
    state_file.write_text("not json at all { { garbage }", encoding="utf-8")

    state_store = TreeStateStore(state_file)
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, state_store=state_store)

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        # App starts normally, selects WS1
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == ws1.id


@pytest.mark.asyncio
async def test_empty_state_file(session: Session, tmp_path: Path) -> None:
    """6. Test that an empty state file uses normal defaults."""
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="WS1", node_kind="workspace"))

    state_file = tmp_path / "test-state.json"
    state_file.touch()

    state_store = TreeStateStore(state_file)
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, state_store=state_store)

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == ws1.id


@pytest.mark.asyncio
async def test_state_updates_on_collapse_and_select(
    session: Session, tmp_path: Path
) -> None:
    """7. Test that state updates in real-time when selecting or collapsing nodes."""
    repo = NodeRepository(session)
    ws = repo.create(Node(name="WS1", node_kind="workspace", sort_order=1))
    folder = repo.create(
        Node(name="F1", node_kind="folder", parent_id=ws.id, sort_order=1)
    )

    state_file = tmp_path / "test-state.json"
    state_store = TreeStateStore(state_file)

    # Initially empty state
    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, state_store=state_store)

    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Expand WS1
        await pilot.press("l")
        await pilot.pause(0.01)

        # Select F1
        await pilot.press("j")
        await pilot.pause(0.01)

        # Read state to verify updates
        screen = app.screen
        screen._update_persistent_state()
        state = screen._current_tree_state

        assert ws.id in state.expanded_node_ids
        assert state.selected_node_id == folder.id

        # Collapse WS1
        await pilot.press("k")  # move back to WS1
        await pilot.press("h")  # collapse WS1
        await pilot.pause(0.01)

        screen._update_persistent_state()
        state = screen._current_tree_state

        assert ws.id not in state.expanded_node_ids
        assert state.selected_node_id == ws.id
