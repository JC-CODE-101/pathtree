"""Tests for the Resource Reference TUI integration."""

from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository, ResourceReferenceRepository
from pathtree.services.node_service import NodeService
from pathtree.services.resource_reference_service import ResourceReferenceService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.widgets.details import NodeDetailsPanel
from pathtree.ui.widgets.tree import NodeTreeView


@pytest.mark.asyncio
async def test_reference_tui_rendering_and_details(
    session: Session, tmp_path: Path
) -> None:
    """Verify that a reference node renders with ↗ and displays correct details."""
    repo = NodeRepository(session)
    ref_repo = ResourceReferenceRepository(session)
    node_service = NodeService(repo)
    ref_service = ResourceReferenceService(node_service, ref_repo)

    # Setup workspaces and resources using node_service
    ws = node_service.create_node(
        name="Main Workspace", node_kind="workspace", auto_layout=True
    )

    # Touch file so validation passes
    (tmp_path / "file.txt").touch()

    orig = node_service.create_node(
        name="My File",
        node_kind="resource",
        resource_type="file",
        path=str(tmp_path / "file.txt"),
        parent_id=ws.id,
        auto_route=True,
    )

    # Let's locate Custom group which was automatically created
    children = node_service.load_children(ws.id)
    custom_group = next(c for c in children if c.name == "Custom")

    # Create reference
    ref_service.create_reference(
        original_node_id=orig.id,
        destination_parent_id=custom_group.id,
        custom_name="My Referenced File",
    )

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)
        details = app.screen.query_one("#details-panel", NodeDetailsPanel)

        # 1. Expand Main Workspace
        await pilot.press("l")
        await pilot.pause(0.05)

        # 2. Go to System
        await pilot.press("j")
        await pilot.pause(0.05)

        # 3. Go to Custom
        await pilot.press("j")
        await pilot.pause(0.05)

        # 4. Expand Custom
        await pilot.press("l")
        await pilot.pause(0.05)

        # 5. Go to My Referenced File
        await pilot.press("j")
        await pilot.pause(0.05)

        # Check highlighted node is the reference node
        assert tree.cursor_node is not None
        ref_node = node_service.get_node(tree.cursor_node.data)
        assert ref_node is not None
        assert ref_node.resource_type == "reference"

        # Check rendering is decorated with ↗
        label = tree.cursor_node.label
        assert "↗" in label.plain

        # Check details panel contains active reference metadata
        content = details.render().plain
        assert "Reference Status: ACTIVE" in content
        assert "Original Name: My File" in content
        assert "Original Type: file" in content
