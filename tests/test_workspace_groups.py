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
        await pilot.pause(0.2)

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
        await pilot.pause(0.2)
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
        await pilot.pause(0.5)

        # Retrieve expansion/selection after tree reload
        current_expansions = tree.get_expanded_node_ids()
        assert group.id in current_expansions
        assert tree.cursor_node.data == ws.id


@pytest.mark.asyncio
async def test_view_state_preservation_across_group_move_and_dissolve(tmp_path) -> None:
    """Rigorous integration test for view state desynchronization (Step 11)."""
    from pathtree.database.connection import create_db_engine, init_db
    from pathtree.database.repository import (
        NodeRepository,
        WorkspaceViewSettingsRepository,
    )
    from pathtree.services.node_service import NodeService
    from pathtree.services.workspace_view_settings_service import (
        WorkspaceViewSettingsService,
    )
    from pathtree.ui.app import PathTreeApp

    db_file = tmp_path / "view_sync_test.db"

    # Step 1-3: Setup via initial services
    engine = create_db_engine(db_file)
    init_db(engine)
    with Session(engine) as session:
        repo = NodeRepository(session)
        service = NodeService(repo)

        python_ws = service.create_node(
            name="Python Workspace", node_kind="workspace", auto_layout=True
        )
        group = service.create_node(name="Group", node_kind="workspace_group")
        service.move_node(python_ws.id, group.id)
        session.commit()

        python_ws_id = python_ws.id
        group_id = group.id

    # Step 4: Launch App, select Python, apply vd, ve
    app = PathTreeApp(node_service=NodeService(NodeRepository(Session(engine))))
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # Select Python Workspace
        tree = app.screen.query_one("#tree-view", NodeTreeView)
        # Expand group first to see Python Workspace
        group_tn = next(child for child in tree.root.children if child.data == group_id)
        tree.move_cursor(group_tn)
        await pilot.press("l")  # Expand Group
        await pilot.pause(0.05)

        # Move to Python Workspace
        python_tn = group_tn.children[0]
        tree.move_cursor(python_tn)
        await pilot.pause(0.05)
        assert tree.cursor_node.data == python_ws_id

        # Apply vd
        await pilot.press("v")
        await pilot.pause(0.01)
        assert app.screen._view_command_active is True
        await pilot.press("d")
        await pilot.pause(0.05)

        # Apply ve
        await pilot.press("v")
        await pilot.pause(0.01)
        assert app.screen._view_command_active is True
        await pilot.press("e")
        await pilot.pause(0.05)

        # Step 5: Dissolve Group (within active app to trigger refresh)
        app.screen.node_service.dissolve_group(group_id)
        app.screen.refresh_tree()
        await pilot.pause(0.1)

    # Dispose old engine
    engine.dispose()

    # Step 6: Recreate engine/session/repository/service/app
    engine2 = create_db_engine(db_file)
    init_db(engine2)
    session2 = Session(engine2)
    repo2 = NodeRepository(session2)
    service2 = NodeService(repo2)

    # Step 7: Select Python & run va (4 times)
    app2 = PathTreeApp(node_service=service2)
    async with app2.run_test(size=(80, 60)) as pilot:
        while app2.screen.id != "main-screen":
            await pilot.pause(0.01)

        # Select Python Workspace
        tree2 = app2.screen.query_one("#tree-view", NodeTreeView)
        python_tn2 = next(
            child for child in tree2.root.children if child.data == python_ws_id
        )
        tree2.move_cursor(python_tn2)
        await pilot.pause(0.05)
        assert tree2.cursor_node.data == python_ws_id

        # Verify initial mode (starts as "all" after first load, toggling will switch to "filter")
        wvs_repo = WorkspaceViewSettingsRepository(session2)
        wvs_service = WorkspaceViewSettingsService(wvs_repo)
        wvs_service.get_settings(python_ws_id)

        # Let's run va 4 times and expect All <-> Filter toggling
        # Since it starts as "filter" (set by vd and ve), the first toggle switches to "all"
        expected_modes = ["all", "filter", "all", "filter"]
        for expected_mode in expected_modes:
            await pilot.press("v")
            await pilot.pause(0.01)
            await pilot.press("a")
            await pilot.pause(0.05)

            # Retrieve from DB directly to assert authoritative state
            session2.commit()
            fresh_settings = wvs_repo.get_by_workspace_id(python_ws_id)
            assert fresh_settings.current_mode == expected_mode

        # Step 11 part 2: Test vv, vv (only hide-empty must change)
        original_hide_empty = fresh_settings.hide_empty_sections
        expected_hide_empty_states = [not original_hide_empty, original_hide_empty]
        for expected_he in expected_hide_empty_states:
            await pilot.press("v")
            await pilot.pause(0.01)
            await pilot.press("v")
            await pilot.pause(0.05)

            session2.commit()
            fresh_settings = wvs_repo.get_by_workspace_id(python_ws_id)
            assert fresh_settings.hide_empty_sections == expected_he

        # Step 11 part 3: Repeat va 20 times. No drift!
        current_expected_mode = "filter"
        for _ in range(20):
            current_expected_mode = (
                "all" if current_expected_mode == "filter" else "filter"
            )
            await pilot.press("v")
            await pilot.pause(0.01)
            await pilot.press("a")
            await pilot.pause(0.05)

            session2.commit()
            fresh_settings = wvs_repo.get_by_workspace_id(python_ws_id)
            assert fresh_settings.current_mode == current_expected_mode

    engine2.dispose()
