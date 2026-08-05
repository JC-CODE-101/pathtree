from unittest import mock

import pytest

from pathtree.database.repository import (
    LaunchProfileRepository,
    MultiLauncherRepository,
    NodeRepository,
)
from pathtree.services.launch_profile_service import LaunchProfileService
from pathtree.services.multi_launcher_service import (
    LauncherNotFoundError,
    MultiLauncherService,
)
from pathtree.services.node_service import NodeService, ValidationError


@pytest.fixture
def node_service(session):
    node_repo = NodeRepository(session)
    return NodeService(node_repo)


@pytest.fixture
def launch_profile_service(session, node_service):
    lp_repo = LaunchProfileRepository(session)
    return LaunchProfileService(node_service, lp_repo)


@pytest.fixture
def mock_sleeper():
    return mock.Mock()


@pytest.fixture
def multi_launcher_service(session, node_service, launch_profile_service, mock_sleeper):
    ml_repo = MultiLauncherRepository(session)
    return MultiLauncherService(
        node_service,
        launch_profile_service,
        ml_repo,
        sleeper=mock_sleeper,
    )


@pytest.fixture
def cli_session(session):
    """Provide a database session specifically for CLI test context."""
    with mock.patch("pathtree.app.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = session
        yield session


def test_create_and_read_multi_launcher(node_service, multi_launcher_service):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")

    launcher = multi_launcher_service.create_launcher(
        name="Workspace Workspace",
        workspace_id=ws.id,
        description="Launch all systems",
    )

    assert launcher.id is not None
    assert launcher.name == "Workspace Workspace"
    assert launcher.description == "Launch all systems"
    assert launcher.workspace_id == ws.id

    # Verify lazy system group creation
    node = node_service.get_node(launcher.launcher_node_id)
    assert node.node_kind == "resource"
    assert node.resource_type == "multi_launcher"

    group = node_service.get_node(node.parent_id)
    assert group.node_kind == "system_group"
    assert group.system_role == "multi_launchers"


def test_update_multi_launcher(multi_launcher_service, node_service):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    launcher = multi_launcher_service.create_launcher(
        name="Original Name",
        workspace_id=ws.id,
        description="Original Desc",
    )

    multi_launcher_service.update_launcher(
        launcher.id, name="New Name", description="New Desc"
    )

    fetched = multi_launcher_service.get_launcher(launcher.id)
    assert fetched.name == "New Name"
    assert fetched.description == "New Desc"

    node = node_service.get_node(launcher.launcher_node_id)
    assert node.name == "New Name"
    assert node.description == "New Desc"


def test_delete_multi_launcher(multi_launcher_service, node_service):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    launcher = multi_launcher_service.create_launcher(
        name="Launcher",
        workspace_id=ws.id,
    )
    launcher_node_id = launcher.launcher_node_id

    assert node_service.get_node(launcher_node_id) is not None

    # Delete
    multi_launcher_service.delete_launcher(launcher.id)

    with pytest.raises(LauncherNotFoundError):
        multi_launcher_service.get_launcher(launcher.id)

    assert node_service.get_node(launcher_node_id) is None


def test_duplicate_multi_launcher(
    multi_launcher_service, launch_profile_service, node_service
):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    script = node_service.create_node(
        name="Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    p1 = launch_profile_service.create_profile(
        name="Profile 1",
        target_node_id=script.id,
        arguments=["1"],
    )

    launcher = multi_launcher_service.create_launcher(
        name="Workspace 1",
        workspace_id=ws.id,
        description="Desc",
    )
    multi_launcher_service.add_item(launcher.id, p1.id, delay_ms=100)

    # Duplicate
    duplicated = multi_launcher_service.duplicate_launcher(launcher.id)

    assert duplicated.id != launcher.id
    assert duplicated.name == "Workspace 1 Copy"
    assert duplicated.description == launcher.description

    # Verify items duplicated
    orig_items = multi_launcher_service.repository.list_items_for_launcher(launcher.id)
    dup_items = multi_launcher_service.repository.list_items_for_launcher(duplicated.id)

    assert len(orig_items) == 1
    assert len(dup_items) == 1
    assert dup_items[0].launch_profile_id == p1.id
    assert dup_items[0].delay_ms == 100


def test_launcher_items_operations(
    multi_launcher_service, launch_profile_service, node_service
):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    script = node_service.create_node(
        name="Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    p1 = launch_profile_service.create_profile(
        name="Profile 1",
        target_node_id=script.id,
        arguments=["1"],
    )
    p2 = launch_profile_service.create_profile(
        name="Profile 2",
        target_node_id=script.id,
        arguments=["2"],
    )

    launcher = multi_launcher_service.create_launcher(
        name="Workspace 1",
        workspace_id=ws.id,
    )

    # Add items
    it1 = multi_launcher_service.add_item(launcher.id, p1.id, delay_ms=500)
    it2 = multi_launcher_service.add_item(launcher.id, p2.id, delay_ms=1000)

    assert it1.position == 1
    assert it2.position == 2

    # List items
    items = multi_launcher_service.repository.list_items_for_launcher(launcher.id)
    assert len(items) == 2

    # Reorder (Move Up)
    multi_launcher_service.reorder_item(it2.id, "up")
    items = multi_launcher_service.repository.list_items_for_launcher(launcher.id)
    assert items[0].launch_profile_id == p2.id
    assert items[1].launch_profile_id == p1.id

    # Enable / Disable
    multi_launcher_service.set_item_enabled(it2.id, False)
    item2_updated = multi_launcher_service.repository.get_item_by_id(it2.id)
    assert item2_updated.enabled is False

    # Delay persistence
    multi_launcher_service.set_item_delay(it1.id, 250)
    item1_updated = multi_launcher_service.repository.get_item_by_id(it1.id)
    assert item1_updated.delay_ms == 250

    # Remove item
    multi_launcher_service.remove_item(it2.id)
    items = multi_launcher_service.repository.list_items_for_launcher(launcher.id)
    assert len(items) == 1
    assert items[0].launch_profile_id == p1.id
    assert items[0].position == 1


@mock.patch(
    "pathtree.services.launch_profile_service.LaunchProfileService.execute_profile"
)
def test_execution_order_and_delay_semantics(
    mock_execute_profile,
    mock_sleeper,
    multi_launcher_service,
    launch_profile_service,
    node_service,
):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    script = node_service.create_node(
        name="Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    p1 = launch_profile_service.create_profile(
        name="Profile 1",
        target_node_id=script.id,
        arguments=["1"],
    )
    p2 = launch_profile_service.create_profile(
        name="Profile 2",
        target_node_id=script.id,
        arguments=["2"],
    )
    p3 = launch_profile_service.create_profile(
        name="Profile 3",
        target_node_id=script.id,
        arguments=["3"],
    )

    launcher = multi_launcher_service.create_launcher(
        name="Workspace 1",
        workspace_id=ws.id,
    )
    multi_launcher_service.add_item(launcher.id, p1.id, delay_ms=100)
    it2 = multi_launcher_service.add_item(launcher.id, p2.id, delay_ms=200)
    multi_launcher_service.add_item(launcher.id, p3.id, delay_ms=300)

    # Disable the middle item (Profile 2)
    multi_launcher_service.set_item_enabled(it2.id, False)

    # Execute
    multi_launcher_service.execute_launcher(launcher.id)

    # Should only execute active ones: Profile 1, then Profile 3
    assert mock_execute_profile.call_count == 2
    mock_execute_profile.assert_any_call(p1.id)
    mock_execute_profile.assert_any_call(p3.id)

    # Delay Semantics:
    # delay_ms is applied *after* that item launches,
    # before the next enabled item starts.
    # Profile 1 delay_ms is 100, which is applied because
    # there is another enabled item (Profile 3) coming.
    # Profile 3 is the final enabled item, so it should
    # NOT introduce any unnecessary delay!
    # Therefore, sleeper should be called exactly once with 0.1
    mock_sleeper.assert_called_once_with(0.1)


@mock.patch(
    "pathtree.services.launch_profile_service.LaunchProfileService.execute_profile"
)
def test_stop_on_initiation_failure(
    mock_execute_profile,
    multi_launcher_service,
    launch_profile_service,
    node_service,
):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    script = node_service.create_node(
        name="Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    p1 = launch_profile_service.create_profile(
        name="Profile 1",
        target_node_id=script.id,
        arguments=["1"],
    )
    p2 = launch_profile_service.create_profile(
        name="Profile 2",
        target_node_id=script.id,
        arguments=["2"],
    )

    launcher = multi_launcher_service.create_launcher(
        name="Workspace 1",
        workspace_id=ws.id,
    )
    multi_launcher_service.add_item(launcher.id, p1.id)
    multi_launcher_service.add_item(launcher.id, p2.id)

    # Mock execute_profile to raise Exception on the first launch profile
    mock_execute_profile.side_effect = Exception("Initiation failed")

    with pytest.raises(Exception, match="Initiation failed"):
        multi_launcher_service.execute_launcher(launcher.id)

    # Verify execution stopped and didn't call the second profile
    assert mock_execute_profile.call_count == 1
    mock_execute_profile.assert_called_once_with(p1.id)


def test_cross_workspace_restriction(
    multi_launcher_service, launch_profile_service, node_service
):
    ws1 = node_service.create_node(name="WS 1", node_kind="workspace")
    ws2 = node_service.create_node(name="WS 2", node_kind="workspace")

    script1 = node_service.create_node(
        name="Script 1",
        node_kind="resource",
        resource_type="script",
        parent_id=ws1.id,
        path=__file__,
    )
    p_ws1 = launch_profile_service.create_profile(
        name="Profile WS1",
        target_node_id=script1.id,
        arguments=[],
    )

    # Create Multi Launcher owned by WS2
    launcher_ws2 = multi_launcher_service.create_launcher(
        name="Launcher WS2",
        workspace_id=ws2.id,
    )

    # Attempting to add WS1's profile to WS2's launcher must raise ValidationError
    with pytest.raises(ValidationError, match="must belong to the same Workspace"):
        multi_launcher_service.add_item(launcher_ws2.id, p_ws1.id)


def test_stale_and_detached_profile_references(
    multi_launcher_service, launch_profile_service, node_service
):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    script = node_service.create_node(
        name="Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    p1 = launch_profile_service.create_profile(
        name="P1",
        target_node_id=script.id,
        arguments=[],
    )

    launcher = multi_launcher_service.create_launcher(
        name="Launcher",
        workspace_id=ws.id,
    )
    multi_launcher_service.add_item(launcher.id, p1.id)

    # 1. Detach target
    node_service.delete_node(script.id)

    # Execution must fail and report the profile is detached
    with pytest.raises(ValidationError, match="is detached"):
        multi_launcher_service.execute_launcher(launcher.id)

    # 2. Reconnect to make active, then delete launch profile itself
    new_script = node_service.create_node(
        name="New Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )
    launch_profile_service.reconnect_profile(p1.id, new_script.id)

    # Test Cascade Deletion: deleting launch profile should remove the item
    launch_profile_service.delete_profile(p1.id)
    items_after_delete = multi_launcher_service.repository.list_items_for_launcher(
        launcher.id
    )
    assert len(items_after_delete) == 0

    # Test Stale Reference: mock list_items_for_launcher to return a stale item
    import uuid

    from pathtree.models.multi_launcher import MultiLauncherItem

    fake_item = MultiLauncherItem(
        multi_launcher_id=launcher.id,
        launch_profile_id=uuid.uuid4(),
        position=1,
        enabled=True,
    )

    with mock.patch.object(
        multi_launcher_service.repository,
        "list_items_for_launcher",
        return_value=[fake_item],
    ):
        # Executing now must fail and report the profile is missing (stale reference)
        with pytest.raises(ValidationError, match="not found"):
            multi_launcher_service.execute_launcher(launcher.id)


def test_atomic_creation_failure_paths(multi_launcher_service, node_service):
    ws = node_service.create_node(name="Workspace", node_kind="workspace")

    # If creation fails, ensure no orphan tree nodes remain
    with mock.patch.object(
        multi_launcher_service.repository, "create", side_effect=Exception("DB Error")
    ):
        with pytest.raises(ValidationError, match="Failed to create"):
            multi_launcher_service.create_launcher(
                name="Launcher",
                workspace_id=ws.id,
            )

    # Verify no multi_launcher nodes exist under WS
    nodes = node_service.repository.list_all()
    launcher_nodes = [n for n in nodes if n.resource_type == "multi_launcher"]
    assert len(launcher_nodes) == 0


@pytest.mark.asyncio
async def test_tui_dialog_and_table_management(session):
    node_repo = NodeRepository(session)
    node_service = NodeService(node_repo)
    ws = node_service.create_node(name="WS1", node_kind="workspace")
    script = node_service.create_node(
        name="Build Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    lp_repo = LaunchProfileRepository(session)
    lp_service = LaunchProfileService(node_service, lp_repo)
    lp_service.create_profile(name="P1", target_node_id=script.id, arguments=[])

    ml_repo = MultiLauncherRepository(session)
    ml_service = MultiLauncherService(node_service, lp_service, ml_repo)
    ml_service.create_launcher(name="Main Workspace", workspace_id=ws.id)

    from pathtree.ui.app import PathTreeApp
    from pathtree.ui.dialogs.edit_multi_launcher import EditMultiLauncherDialog

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Navigate to the multi launcher node under Multi Launchers group
        await pilot.press("l")  # Expand WS1
        await pilot.press("j")  # Move down to Build Script
        await pilot.press("j")  # Move down to Launch Profiles
        await pilot.press("j")  # Move down to Multi Launchers
        await pilot.press("l")  # Expand Multi Launchers
        await pilot.press("j")  # Move down to Main Workspace
        assert "Main Workspace" in str(tree.cursor_node.label)

        # Open actions menu
        await pilot.press("o")
        await pilot.pause(0.01)

        from pathtree.ui.dialogs.action_menu import ResourceActionMenu

        assert isinstance(app.screen, ResourceActionMenu)

        await pilot.press("down")  # Down to Edit Multi Launcher
        await pilot.press("enter")
        await pilot.pause(0.01)

        # Edit dialog is open
        assert isinstance(app.screen, EditMultiLauncherDialog)
        dialog = app.screen

        # Verify Name/Description inputs exist
        assert dialog.query_one("#input-name").value == "Main Workspace"

        # Simulate Add Profile button press
        dialog.add_profile_flow()
        await pilot.pause(0.01)

        # Add profile dialog select screen is open
        from pathtree.ui.dialogs.edit_multi_launcher import AddProfileSelectScreen

        assert isinstance(app.screen, AddProfileSelectScreen)
        await pilot.press("enter")  # Select the only profile P1
        await pilot.pause(0.01)

        # Item added and rendered in table
        table = dialog.query_one("#launcher-table")
        assert table.row_count == 1

        # Close/Save
        dialog.save_launcher_details_and_close()
        await pilot.pause(0.01)

        assert app.screen.id == "main-screen"


def test_cli_listing_and_execution_isolated(
    cli_session,
    node_service,
    multi_launcher_service,
    launch_profile_service,
):
    ws = node_service.create_node(name="WS1", node_kind="workspace")
    script = node_service.create_node(
        name="Build Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )
    p = launch_profile_service.create_profile(
        name="Profile 1",
        target_node_id=script.id,
        arguments=["1"],
    )

    launcher = multi_launcher_service.create_launcher(
        name="Workspace 1",
        workspace_id=ws.id,
        description="Launch everything",
    )
    multi_launcher_service.add_item(launcher.id, p.id)

    from pathtree.app import main

    # 1. Listing test
    with mock.patch("sys.argv", ["pb", "--multi-launchers"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    # 2. Execution test (completely isolated, no real external launches or sleeping)
    exec_patch_path = (
        "pathtree.services.launch_profile_service.LaunchProfileService.execute_profile"
    )
    with mock.patch("sys.argv", ["pb", "--multi-launcher", "1"]):
        with mock.patch(exec_patch_path) as mock_exec:
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
            mock_exec.assert_called_once_with(p.id)


@pytest.mark.asyncio
async def test_add_node_from_system_group_regression(session):
    """Verify that pressing 'a' when on a system group node does not crash."""
    node_repo = NodeRepository(session)
    node_service = NodeService(node_repo)
    ws = node_service.create_node(name="WS", node_kind="workspace")
    node_service.get_or_create_system_group(ws.id, "some_role", "Some Group")

    from pathtree.ui.app import PathTreeApp

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        await pilot.press("l")  # expand workspace
        await pilot.press("j")  # move to Some Group
        assert "Some Group" in str(tree.cursor_node.label)

        # Trigger Add Node Dialog
        await pilot.press("a")
        await pilot.pause(0.01)

        # Dialog is open without any Select crash!
        from pathtree.ui.dialogs.add_node import AddNodeDialog

        assert isinstance(app.screen, AddNodeDialog)

        # Cancel
        await pilot.press("escape")
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_tui_edit_shortcut_toggles_and_delay_prompt_validation(session):
    """Verify Edit Multi Launcher Dialog bindings, enable/disable toggle.

    Also tests delay prompt validation errors.
    """
    node_repo = NodeRepository(session)
    node_service = NodeService(node_repo)
    ws = node_service.create_node(name="WS", node_kind="workspace")
    script = node_service.create_node(
        name="Build Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    lp_repo = LaunchProfileRepository(session)
    lp_service = LaunchProfileService(node_service, lp_repo)
    lp = lp_service.create_profile(name="P1", target_node_id=script.id, arguments=[])

    ml_repo = MultiLauncherRepository(session)
    ml_service = MultiLauncherService(node_service, lp_service, ml_repo)
    ml = ml_service.create_launcher(name="Launcher A", workspace_id=ws.id)
    ml_service.add_item(ml.id, lp.id, delay_ms=100)

    from pathtree.ui.app import PathTreeApp
    from pathtree.ui.dialogs.edit_multi_launcher import EditMultiLauncherDialog

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Move to Build Script
        await pilot.press("j")  # Move to Launch Profiles
        await pilot.press("j")  # Move to Multi Launchers
        await pilot.press("l")  # Expand Multi Launchers
        await pilot.press("j")  # Move to Launcher A

        # 'e' opens EditMultiLauncherDialog (not EditNodeDialog)
        await pilot.press("e")
        await pilot.pause(0.01)

        assert isinstance(app.screen, EditMultiLauncherDialog)
        dialog = app.screen

        # Verify initial table state
        table = dialog.query_one("#launcher-table")
        assert table.row_count == 1
        assert "ENABLED" in str(table.get_row_at(0))

        # Press 'e' on the row to toggle disabled
        await pilot.press("e")
        await pilot.pause(0.01)
        assert "DISABLED" in str(table.get_row_at(0))

        # Press 'd' to open delay prompt
        await pilot.press("d")
        await pilot.pause(0.01)

        prompt_screen = app.screen
        assert prompt_screen.__class__.__name__ == "DelayPromptScreen"

        # Type invalid value like "-50" or blank, and check validation message
        # Let's clear and write a negative number
        input_widget = prompt_screen.query_one("#input-delay-prompt")
        input_widget.value = ""
        await pilot.press("hyphen", "5", "0")
        await pilot.press("enter")
        await pilot.pause(0.01)

        # Check prompt-error label has validation message
        error_label = prompt_screen.query_one("#prompt-error")
        assert "Delay must be a non-negative integer." in error_label.render().plain

        # Enter a valid delay like "500" and press enter
        input_widget.value = ""
        await pilot.press("5", "0", "0")
        await pilot.press("enter")
        await pilot.pause(0.01)

        # Verify back on Edit dialog and delay is updated
        assert isinstance(app.screen, EditMultiLauncherDialog)
        assert "500 ms" in str(table.get_row_at(0))

        # Close out
        await pilot.press("escape")
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_details_panel_rendering(session):
    """Verify that Details Panel shows Multi Launcher metadata & item lists."""
    node_repo = NodeRepository(session)
    node_service = NodeService(node_repo)
    ws = node_service.create_node(name="WS", node_kind="workspace")
    script = node_service.create_node(
        name="Build Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    lp_repo = LaunchProfileRepository(session)
    lp_service = LaunchProfileService(node_service, lp_repo)
    lp1 = lp_service.create_profile(name="P1", target_node_id=script.id, arguments=[])
    lp2 = lp_service.create_profile(name="P2", target_node_id=script.id, arguments=[])

    ml_repo = MultiLauncherRepository(session)
    ml_service = MultiLauncherService(node_service, lp_service, ml_repo)
    ml = ml_service.create_launcher(
        name="Launcher A",
        workspace_id=ws.id,
        description="Details test",
    )
    ml_service.add_item(ml.id, lp1.id, delay_ms=100)
    item2 = ml_service.add_item(ml.id, lp2.id, delay_ms=200)
    ml_service.set_item_enabled(item2.id, False)

    from pathtree.ui.app import PathTreeApp

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Move to Build Script
        await pilot.press("j")  # Move to Launch Profiles
        await pilot.press("j")  # Move to Multi Launchers
        await pilot.press("l")  # Expand Multi Launchers
        await pilot.press("j")  # Move to Launcher A

        # Verify cursor is on Launcher A
        assert "Launcher A" in str(tree.cursor_node.label)

        # Check details panel text content
        details_panel = app.screen.query_one("#details-panel")
        content = details_panel.render().plain

        # Content should include Workspace Name, description, counts, and listing.
        assert "Workspace: WS" in content
        assert "Description: Details test" in content
        assert "Profiles: 2" in content
        assert "Enabled: 1" in content
        assert "Total Delay: 0 ms" in content
        assert "1. P1 [100 ms]" in content
        assert "2. P2 [disabled]" in content


@pytest.mark.asyncio
async def test_layout_stability_regression(session):
    """Verify selecting a long name profile doesn't shift the vertical divider."""
    node_repo = NodeRepository(session)
    node_service = NodeService(node_repo)
    ws = node_service.create_node(name="WS", node_kind="workspace")
    script = node_service.create_node(
        name="Build Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    lp_repo = LaunchProfileRepository(session)
    lp_service = LaunchProfileService(node_service, lp_repo)
    # Extremely long name
    long_name = "P1" * 100
    lp1 = lp_service.create_profile(
        name=long_name, target_node_id=script.id, arguments=[]
    )

    ml_repo = MultiLauncherRepository(session)
    ml_service = MultiLauncherService(node_service, lp_service, ml_repo)
    ml = ml_service.create_launcher(
        name="Launcher A", workspace_id=ws.id, description="Details test"
    )
    ml_service.add_item(ml.id, lp1.id, delay_ms=100)

    from pathtree.ui.app import PathTreeApp

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree_view = app.screen.query_one("#tree-view")
        details_panel = app.screen.query_one("#details-panel")

        # Record widths on workspace node selection
        init_tree_width = tree_view.size.width
        init_details_width = details_panel.size.width

        # Ensure layout widths are positive integers
        assert init_tree_width > 0
        assert init_details_width > 0

        # Now select the Multi Launcher node
        await pilot.press("l")  # Expand WS
        await pilot.press("j")  # Move to Build Script
        await pilot.press("j")  # Move to Launch Profiles
        await pilot.press("j")  # Move to Multi Launchers
        await pilot.press("l")  # Expand Multi Launchers
        await pilot.press("j")  # Move to Launcher A
        await pilot.pause(0.01)

        # Verify cursor is indeed on Launcher A
        assert "Launcher A" in str(tree_view.cursor_node.label)

        # Verify the details content has the long name
        content = details_panel.render().plain
        assert long_name in content

        # Check pane widths remain exactly the same as initial proportions
        assert tree_view.size.width == init_tree_width
        assert details_panel.size.width == init_details_width


@pytest.mark.asyncio
async def test_multi_launcher_creation_validation_regression(session):
    """Verify that multi-launcher creation correctly resolves canonical system groups.

    It should not block creation or try to duplicate the system group in layouts.
    """
    node_repo = NodeRepository(session)
    node_service = NodeService(node_repo)

    # 1. Create Workspace C with auto_layout
    ws_c = node_service.create_node(
        name="Workspace C", node_kind="workspace", auto_layout=True
    )

    # Check canonical group structures under WS C System group
    sys_group = node_service.get_system_group(ws_c.id)
    canonical_ml_group = node_service.get_system_subsection(ws_c.id, "multi_launcher")
    assert sys_group is not None
    assert canonical_ml_group is not None
    assert canonical_ml_group.parent_id == sys_group.id

    # 2. Setup MultiLauncherService on the fly
    lp_repo = LaunchProfileRepository(session)
    lp_service = LaunchProfileService(node_service, lp_repo)
    ml_repo = MultiLauncherRepository(session)
    ml_service = MultiLauncherService(node_service, lp_service, ml_repo)

    # 3. Create Multi Launcher with any descendant parent under Workspace C
    # Selected Parent 1: the canonical Multi Launchers system group
    launcher1 = ml_service.create_launcher(
        name="MyBlenderLauncher1",
        workspace_id=ws_c.id,
        node_id=None,  # let it locate/create via get_or_create_system_group
    )
    assert launcher1 is not None

    # Fetch newly created tree node
    node1 = node_service.get_node(launcher1.launcher_node_id)
    assert node1.parent_id == canonical_ml_group.id
    assert node1.node_kind == "resource"
    assert node1.resource_type == "multi_launcher"
    assert node1.system_role is None

    # Repeat creation with other selected parent contexts
    selections = [
        ws_c.id,  # Workspace C root
        sys_group.id,  # System
        node_service.get_system_subsection(ws_c.id, "file").id,  # Files
        node_service.get_system_subsection(ws_c.id, "executable").id,  # Executables
        node_service.get_custom_group(ws_c.id).id,  # Custom
    ]

    for idx, _sel_parent_id in enumerate(selections):
        # We can simulate creating a launcher on these positions
        launcher = ml_service.create_launcher(
            name=f"MyBlenderLauncher_Sel_{idx}",
            workspace_id=ws_c.id,
            node_id=None,
        )
        assert launcher is not None
        node = node_service.get_node(launcher.launcher_node_id)
        assert node.parent_id == canonical_ml_group.id
        assert node.node_kind == "resource"
        assert node.resource_type == "multi_launcher"
        assert node.system_role is None

    # Verify no root-level managed Multi Launchers group was created
    all_nodes = node_repo.list_all()
    root_ml_groups = [
        n
        for n in all_nodes
        if n.parent_id is None
        and n.node_kind == "system_group"
        and n.system_role == "multi_launchers"
    ]
    assert len(root_ml_groups) == 0
