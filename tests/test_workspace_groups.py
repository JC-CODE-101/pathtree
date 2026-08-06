import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.services.node_service import NodeService, ValidationError
from pathtree.ui.app import PathTreeApp
from pathtree.ui.widgets.tree import NodeTreeView


@pytest.fixture(name="node_service")
def node_service_fixture(session: Session) -> NodeService:
    """Fixture for NodeService initialized with the test repository."""
    repo = NodeRepository(session)
    return NodeService(repo)


def test_create_workspace_group(node_service: NodeService) -> None:
    """Test creating a workspace group under Root."""
    group = node_service.create_node(name="Group A", node_kind="workspace_group")
    assert group.name == "Group A"
    assert group.node_kind == "workspace_group"
    assert group.parent_id is None

    # Nested groups are explicitly NOT supported
    with pytest.raises(ValidationError):
        node_service.create_node(
            name="Sub Group", node_kind="workspace_group", parent_id=group.id
        )


def test_create_workspace_inside_group(node_service: NodeService) -> None:
    """Test creating a workspace inside a group."""
    group = node_service.create_node(name="Group A", node_kind="workspace_group")
    ws = node_service.create_node(
        name="Workspace Inside", node_kind="workspace", parent_id=group.id
    )
    assert ws.name == "Workspace Inside"
    assert ws.node_kind == "workspace"
    assert ws.parent_id == group.id


def test_create_workspace_under_root(node_service: NodeService) -> None:
    """Test creating a workspace under Root (None)."""
    ws = node_service.create_node(
        name="Workspace Root", node_kind="workspace", parent_id=None
    )
    assert ws.name == "Workspace Root"
    assert ws.node_kind == "workspace"
    assert ws.parent_id is None


def test_workspace_group_restrictions(node_service: NodeService) -> None:
    """Test that groups may NOT contain other node types."""
    group = node_service.create_node(name="Group A", node_kind="workspace_group")

    # Groups may not contain folders
    with pytest.raises(ValidationError):
        node_service.create_node(name="Folder", node_kind="folder", parent_id=group.id)

    # Groups may not contain resources
    with pytest.raises(ValidationError):
        node_service.create_node(
            name="File",
            node_kind="resource",
            resource_type="file",
            parent_id=group.id,
            path="/some/file.txt",
        )


def test_move_workspace_between_groups_and_root(node_service: NodeService) -> None:
    """Test moving a Workspace between groups and back to ROOT."""
    group_a = node_service.create_node(name="Group A", node_kind="workspace_group")
    group_b = node_service.create_node(name="Group B", node_kind="workspace_group")
    ws = node_service.create_node(
        name="Workspace", node_kind="workspace", parent_id=group_a.id
    )

    # Move to group_b
    moved = node_service.move_node(ws.id, group_b.id)
    assert moved.parent_id == group_b.id

    # Move back to ROOT (None)
    moved_back = node_service.move_node(ws.id, None)
    assert moved_back.parent_id is None


def test_dissolve_populated_group(node_service: NodeService) -> None:
    """Test dissolving a populated group reparents child workspaces to ROOT."""
    group = node_service.create_node(name="Group A", node_kind="workspace_group")
    ws_a = node_service.create_node(
        name="WS A", node_kind="workspace", parent_id=group.id
    )
    ws_b = node_service.create_node(
        name="WS B", node_kind="workspace", parent_id=group.id
    )

    # Dissolve group
    success = node_service.dissolve_group(group.id)
    assert success is True

    # Check workspaces are now under ROOT
    fresh_ws_a = node_service.get_node(ws_a.id)
    fresh_ws_b = node_service.get_node(ws_b.id)
    assert fresh_ws_a.parent_id is None
    assert fresh_ws_b.parent_id is None

    # Group node is deleted
    assert node_service.get_node(group.id) is None


def test_dissolve_empty_group(node_service: NodeService) -> None:
    """Test dissolving an empty group immediately succeeds."""
    group = node_service.create_node(name="Group A", node_kind="workspace_group")
    success = node_service.dissolve_group(group.id)
    assert success is True
    assert node_service.get_node(group.id) is None


def test_rename_group(node_service: NodeService) -> None:
    """Test renaming a group."""
    group = node_service.create_node(name="Group A", node_kind="workspace_group")
    updated = node_service.update_node(group.id, name="New Group Name")
    assert updated.name == "New Group Name"


@pytest.mark.asyncio
async def test_tui_focus_group_and_leave_focus(session: Session) -> None:
    """Test focus group action and leaving focus mode in MainScreen."""
    repo = NodeRepository(session)
    service = NodeService(repo)

    # Setup database with workspace group and other workspaces
    group = service.create_node(name="Focused Group", node_kind="workspace_group")
    ws_focused = service.create_node(
        name="WS Focused", node_kind="workspace", parent_id=group.id, auto_layout=True
    )
    ws_other = service.create_node(
        name="WS Other", node_kind="workspace", parent_id=None, auto_layout=True
    )

    app = PathTreeApp(node_service=service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # Verify initial focus state is None
        assert app.screen._focused_group_id is None

        # Focus group
        app.screen._focused_group_id = group.id
        app.screen._last_selected_node_id = ws_focused.id

        # Call refresh_tree to apply focus mode filtering
        app.screen.refresh_tree(selected_node_id=ws_focused.id)
        await pilot.pause(0.1)

        # Verify that WS Other is NOT visible, but WS Focused is visible
        tree = app.screen.query_one("#tree-view", NodeTreeView)
        visible_ids = [
            node.data for node in tree.get_visible_nodes() if node.data is not None
        ]
        assert ws_focused.id in visible_ids
        assert ws_other.id not in visible_ids

        # Leave focus mode by triggering action
        app.screen.action_leave_focus()
        assert app.screen._focused_group_id is None

        # Refresh tree and verify both workspaces are visible again
        app.screen.refresh_tree(selected_node_id=ws_focused.id)
        await pilot.pause(0.1)
        visible_ids_full = [
            node.data for node in tree.get_visible_nodes() if node.data is not None
        ]
        assert ws_focused.id in visible_ids_full
        assert ws_other.id in visible_ids_full


@pytest.mark.asyncio
async def test_tui_expansion_and_selection_preservation(session: Session) -> None:
    """Test that expansion and selection state are properly preserved."""
    repo = NodeRepository(session)
    service = NodeService(repo)

    group = service.create_node(name="Group", node_kind="workspace_group")
    ws = service.create_node(
        name="Workspace", node_kind="workspace", parent_id=group.id, auto_layout=True
    )

    app = PathTreeApp(node_service=service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # Set selection and expansions
        expanded_ids = {group.id, ws.id}
        selected_id = ws.id

        app.screen.refresh_tree(
            selected_node_id=selected_id, expanded_node_ids=expanded_ids
        )
        await pilot.pause(0.1)

        # Retrieve expansion/selection after tree reload
        current_expansions = tree.get_expanded_node_ids()
        assert group.id in current_expansions
        assert tree.cursor_node.data == ws.id
