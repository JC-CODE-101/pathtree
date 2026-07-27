import uuid
from pathlib import Path
from unittest import mock

import pytest

from pathtree.database.repository import LaunchProfileRepository, NodeRepository
from pathtree.services.launch_profile_service import (
    DetachedProfileError,
    InvalidTargetTypeError,
    LaunchProfileService,
    LaunchProfileServiceError,
    ProfileNotFoundError,
)
from pathtree.services.node_service import (
    NodeService,
)
from pathtree.utils.launcher import ProcessLaunchResult


@pytest.fixture
def node_service(session):
    node_repo = NodeRepository(session)
    return NodeService(node_repo)


@pytest.fixture
def launch_profile_service(session, node_service):
    lp_repo = LaunchProfileRepository(session)
    return LaunchProfileService(node_service, lp_repo)


def test_create_and_read_launch_profile(session, node_service, launch_profile_service):
    # Setup workspace
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")

    # Setup script target (must exist on filesystem for NodeService, but let's mock/use a real temp file or bypass path check by using folder or file)
    # Wait, NodeService.create_node for "script" validates path existence!
    # Let's create a real temporary file or folder on disk, or use __file__ as a quick hack!
    script_path = __file__  # exists and is a file!
    script_node = node_service.create_node(
        name="Test Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=script_path,
    )

    # Create launch profile
    profile = launch_profile_service.create_profile(
        name="Default Run",
        target_node_id=script_node.id,
        arguments=["--verbose", "1"],
        terminal_mode="inherit",
    )

    assert profile.id is not None
    assert profile.status == "active"
    assert profile.argv == ["--verbose", "1"]
    assert profile.terminal_mode == "inherit"
    assert profile.target_resource_type == "script"

    # Verify that the launch profiles system group is created under workspace
    launch_profiles_group = node_service.repository.get_by_id(
        profile.profile_node_id
    ).parent_id
    group_node = node_service.repository.get_by_id(launch_profiles_group)
    assert group_node.node_kind == "system_group"
    assert group_node.system_role == "launch_profiles"

    # Get profile by ID
    fetched = launch_profile_service.get_profile(profile.id)
    assert fetched.id == profile.id

    # Get profile for node ID
    fetched_by_node = launch_profile_service.get_profile_for_node(
        profile.profile_node_id
    )
    assert fetched_by_node.id == profile.id


def test_create_profile_unsupported_target(
    session, node_service, launch_profile_service
):
    # Setup workspace
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    # Folder is not a valid target type (must be script or executable)
    folder = node_service.create_node(
        name="My Folder", node_kind="folder", parent_id=ws.id
    )

    with pytest.raises(InvalidTargetTypeError):
        launch_profile_service.create_profile(
            name="Run Folder",
            target_node_id=folder.id,
            arguments=[],
        )


def test_create_profile_working_directory(
    session, node_service, launch_profile_service
):
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    script_node = node_service.create_node(
        name="Test Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    # Let's create a directory node to act as working directory
    # Directory path doesn't strictly have to exist for directory kind (or wait, let's verify if normalize_path/Path checks directory existence. Directory node creation doesn't enforce existence, unlike file/script/executable).
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_node = node_service.create_node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
            path=tmp_dir,
        )

        profile = launch_profile_service.create_profile(
            name="Run in Dir",
            target_node_id=script_node.id,
            arguments=[],
            working_directory_node_id=dir_node.id,
        )
        assert profile.working_directory_node_id == dir_node.id

        # Verify resolution
        resolved_wd = launch_profile_service.resolve_working_directory(profile.id)
        assert str(resolved_wd) == str(Path(tmp_dir).absolute())


def test_update_profile_and_reconnect(session, node_service, launch_profile_service):
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    script_node1 = node_service.create_node(
        name="Test Script 1",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )
    script_node2 = node_service.create_node(
        name="Test Script 2",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    profile = launch_profile_service.create_profile(
        name="Default Run",
        target_node_id=script_node1.id,
        arguments=["--verbose"],
    )

    # Update arguments & name
    launch_profile_service.update_profile(
        profile.id,
        name="New Run Name",
        arguments=["--quiet"],
    )

    fetched = launch_profile_service.get_profile(profile.id)
    assert fetched.argv == ["--quiet"]

    profile_node = node_service.get_node(profile.profile_node_id)
    assert profile_node.name == "New Run Name"

    # Reconnect target compatibility test:
    # Originally Script, so must reconnect only to Script
    # Let's mock or create a mock executable node first
    # Executable creation validates launchability and existence, which is platform specific.
    # We can use node_service directly to create node, let's see.
    # To check that reconnect rejects incompatible target, we can try to reconnect to a Folder or something.
    folder = node_service.create_node(
        name="Some Folder", node_kind="folder", parent_id=ws.id
    )
    with pytest.raises(InvalidTargetTypeError):
        launch_profile_service.reconnect_profile(profile.id, folder.id)

    # Reconnecting to script_node2 should succeed
    launch_profile_service.reconnect_profile(profile.id, script_node2.id)
    fetched = launch_profile_service.get_profile(profile.id)
    assert fetched.target_node_id == script_node2.id


def test_target_deletion_and_detaching(session, node_service, launch_profile_service):
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    script_node = node_service.create_node(
        name="Target Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    profile = launch_profile_service.create_profile(
        name="Run Profile",
        target_node_id=script_node.id,
        arguments=["abc"],
    )

    # Verify active state
    profile_node = node_service.get_node(profile.profile_node_id)
    assert profile_node.parent_id is not None

    # Delete target script node
    node_service.delete_node(script_node.id)

    # Check profile state
    profile_fetched = launch_profile_service.get_profile(profile.id)
    assert profile_fetched.target_node_id is None
    assert profile_fetched.status == "detached"
    assert profile_fetched.previous_target_name == "Target Script"
    assert profile_fetched.previous_target_path == __file__

    # Verify profile node was moved under the "Detached Profiles" system group
    profile_node_updated = node_service.get_node(profile.profile_node_id)
    detached_group_node = node_service.get_node(profile_node_updated.parent_id)
    assert detached_group_node.node_kind == "system_group"
    assert detached_group_node.system_role == "detached_launch_profiles"

    # Reject execution while detached
    with pytest.raises(DetachedProfileError):
        launch_profile_service.execute_profile(profile.id)

    # Reconnect target to a newly created compatible script
    new_script_node = node_service.create_node(
        name="New Target Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )
    launch_profile_service.reconnect_profile(profile.id, new_script_node.id)

    profile_fetched2 = launch_profile_service.get_profile(profile.id)
    assert profile_fetched2.target_node_id == new_script_node.id
    assert profile_fetched2.status == "active"
    assert profile_fetched2.previous_target_name is None
    assert profile_fetched2.previous_target_path is None

    # Verify profile node moved back under Launch Profiles
    profile_node_reconnected = node_service.get_node(profile.profile_node_id)
    launch_group_node = node_service.get_node(profile_node_reconnected.parent_id)
    assert launch_group_node.system_role == "launch_profiles"


def test_directory_deletion_resets_working_directory(
    session, node_service, launch_profile_service
):
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    script_node = node_service.create_node(
        name="Target Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_node = node_service.create_node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
            path=tmp_dir,
        )

        profile = launch_profile_service.create_profile(
            name="Run Profile",
            target_node_id=script_node.id,
            arguments=[],
            working_directory_node_id=dir_node.id,
        )

        assert profile.working_directory_node_id == dir_node.id

        # Delete working directory node
        node_service.delete_node(dir_node.id)

        # Profile working directory must be reset to NULL, but the profile remains active and not deleted!
        profile_fetched = launch_profile_service.get_profile(profile.id)
        assert profile_fetched.working_directory_node_id is None
        assert profile_fetched.status == "active"


def test_delete_profile_removes_both_record_and_node(
    session, node_service, launch_profile_service
):
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    script_node = node_service.create_node(
        name="Target Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    profile = launch_profile_service.create_profile(
        name="Delete Me",
        target_node_id=script_node.id,
        arguments=[],
    )

    profile_node_id = profile.profile_node_id
    assert node_service.get_node(profile_node_id) is not None

    # Delete profile via service
    launch_profile_service.delete_profile(profile.id)

    # Verify both are deleted
    with pytest.raises(ProfileNotFoundError):
        launch_profile_service.get_profile(profile.id)
    assert node_service.get_node(profile_node_id) is None


def test_delete_profile_node_removes_record(
    session, node_service, launch_profile_service
):
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    script_node = node_service.create_node(
        name="Target Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    profile = launch_profile_service.create_profile(
        name="Delete Node Me",
        target_node_id=script_node.id,
        arguments=[],
    )

    # Delete node directly
    node_service.delete_node(profile.profile_node_id)

    # LaunchProfile record should be deleted automatically
    with pytest.raises(ProfileNotFoundError):
        launch_profile_service.get_profile(profile.id)


@mock.patch("pathtree.utils.launcher.PlatformLauncher.launch_process")
def test_execute_profile_success(
    mock_launch_process, session, node_service, launch_profile_service
):
    mock_launch_process.return_value = ProcessLaunchResult(success=True, pid=123)

    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    script_node = node_service.create_node(
        name="Target Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    profile = launch_profile_service.create_profile(
        name="Run Profile",
        target_node_id=script_node.id,
        arguments=["--flag", "val"],
    )

    result = launch_profile_service.execute_profile(profile.id)
    assert result.success is True
    assert result.pid == 123

    # Ensure launch_process was called with correct argv list and parent of __file__ as cwd
    mock_launch_process.assert_called_once()
    called_argv, kwargs = mock_launch_process.call_args
    assert "--flag" in called_argv[0]
    assert "val" in called_argv[0]
    assert kwargs["cwd"] == Path(__file__).parent


@pytest.mark.asyncio
async def test_ui_create_launch_profile(session):
    # Setup database with a script node
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

    from pathtree.ui.app import PathTreeApp
    from pathtree.ui.dialogs.edit_profile import EditProfileDialog

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Navigate to the script node
        await pilot.press("l")  # Expand WS1
        await pilot.press("j")  # Move to Build Script
        assert str(tree.cursor_node.label) == "Build Script"

        # Open action menu
        await pilot.press("o")
        await pilot.pause(0.01)

        # Confirm we are on action menu
        from pathtree.ui.dialogs.action_menu import ResourceActionMenu

        assert isinstance(app.screen, ResourceActionMenu)

        # Select "Create Launch Profile" (we can do so by highlighting / clicking or manual message posting)
        menu = app.screen
        options = [opt.id for opt in menu.actions]
        idx = options.index("create_launch_profile")
        for _ in range(idx):
            await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause(0.01)

        # Dialog is open
        assert isinstance(app.screen, EditProfileDialog)
        dialog = app.screen

        # Type profile name and save
        dialog.query_one("#input-name").value = "Custom Build"
        dialog.query_one("#input-arguments").value = "--mode production"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Back to main screen
        assert app.screen.id == "main-screen"

        # Verify profile is created in DB
        lp_repo = LaunchProfileRepository(session)
        profiles = lp_repo.list_by_target(script.id)
        assert len(profiles) == 1
        assert profiles[0].argv == ["--mode", "production"]


@pytest.mark.asyncio
async def test_ui_edit_launch_profile(session):
    # Setup database with a script and launch profile
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

    from pathtree.database.repository import LaunchProfileRepository
    from pathtree.services.launch_profile_service import LaunchProfileService

    lp_repo = LaunchProfileRepository(session)
    lp_service = LaunchProfileService(node_service, lp_repo)

    profile = lp_service.create_profile(
        name="Build Prof",
        target_node_id=script.id,
        arguments=["--verbose"],
    )

    from pathtree.ui.app import PathTreeApp
    from pathtree.ui.dialogs.edit_profile import EditProfileDialog

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Navigate to the launch profile node
        await pilot.press("l")  # Expand WS1
        await pilot.pause(0.02)
        await pilot.press("j")  # Move to Build Script
        await pilot.press("j")  # Move to Launch Profiles group
        await pilot.press("l")  # Expand group
        await pilot.pause(0.02)
        await pilot.press("j")  # Move to Build Prof node
        assert str(tree.cursor_node.label) == "Build Prof"

        node_id = tree.cursor_node.data
        node_val = node_service.get_node(node_id)
        print(
            "CURSOR NODE DETAILS:",
            str(tree.cursor_node.label),
            "ID:",
            node_id,
            "KIND:",
            getattr(node_val, "node_kind", None),
            "TYPE:",
            getattr(node_val, "resource_type", None),
        )

        # Trigger edit dialog via 'e'
        await pilot.press("e")
        await pilot.pause(0.01)

        # Dialog is open
        assert isinstance(app.screen, EditProfileDialog)
        dialog = app.screen

        # Type profile name and save
        dialog.query_one("#input-name").value = "Build Prof Edited"
        dialog.query_one("#input-arguments").value = "--mode dev"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Back to main screen
        assert app.screen.id == "main-screen"

        # Verify profile is updated in DB
        fetched = lp_service.get_profile(profile.id)
        assert fetched.argv == ["--mode", "dev"]

        # Verify node name is updated
        profile_node = node_service.get_node(profile.profile_node_id)
        assert profile_node.name == "Build Prof Edited"


def test_duplicate_profile_behavior(session, node_service, launch_profile_service):
    # Setup workspace
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    script = node_service.create_node(
        name="Target Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    import tempfile

    with tempfile.TemporaryDirectory() as tmp_dir:
        dir_node = node_service.create_node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
            path=tmp_dir,
        )

        profile = launch_profile_service.create_profile(
            name="Run Blender",
            target_node_id=script.id,
            arguments=["--normal"],
            working_directory_node_id=dir_node.id,
            terminal_mode="new_terminal",
        )

        # 1. Successful duplication
        dup = launch_profile_service.duplicate_profile(profile.id)
        assert dup.id is not None
        assert dup.id != profile.id

        # 2. Copied arguments and settings
        assert dup.argv == ["--normal"]
        assert dup.working_directory_node_id == dir_node.id
        assert dup.terminal_mode == "new_terminal"
        assert dup.target_node_id == script.id
        assert dup.target_resource_type == "script"

        # 3. Unique generated name check
        dup_node = node_service.get_node(dup.profile_node_id)
        assert dup_node.name == "Run Blender Copy"

        # Duplicate again to check incremental unique names: "Run Blender Copy 2"
        dup2 = launch_profile_service.duplicate_profile(profile.id)
        dup_node2 = node_service.get_node(dup2.profile_node_id)
        assert dup_node2.name == "Run Blender Copy 2"

        # 4. Independent editing after duplication
        launch_profile_service.update_profile(dup.id, arguments=["--custom-flag"])

        # Verify orig is unchanged
        orig_fetched = launch_profile_service.get_profile(profile.id)
        assert orig_fetched.argv == ["--normal"]

        # Verify dup is updated
        dup_fetched = launch_profile_service.get_profile(dup.id)
        assert dup_fetched.argv == ["--custom-flag"]

        # 5. Duplicate name rejection
        # If we try to create/update a sibling node to an exact duplicate name, NodeService rejects it
        from pathtree.services.node_service import DuplicateSiblingNameError

        with pytest.raises(DuplicateSiblingNameError):
            node_service.create_node(
                name="Run Blender Copy",
                node_kind="resource",
                resource_type="launch_profile",
                parent_id=dup_node.parent_id,
            )

        # 6. No partial profile or orphan node after failure
        # Mock launch_profile_repository.create to fail
        original_create = launch_profile_service.launch_profile_repository.create
        try:
            from unittest.mock import MagicMock

            launch_profile_service.launch_profile_repository.create = MagicMock(
                side_effect=Exception("DB Failure")
            )
            with pytest.raises(LaunchProfileServiceError):
                launch_profile_service.duplicate_profile(profile.id)

            # Verify no orphan node exists (Run Blender Copy 3 should be deleted and not exist in DB)
            all_nodes = node_service.repository.list_all()
            profile_node_names = [n.name for n in all_nodes]
            assert "Run Blender Copy 3" not in profile_node_names
        finally:
            launch_profile_service.launch_profile_repository.create = original_create


@pytest.mark.asyncio
async def test_add_node_dialog_regression(session):
    # Regression test for "Add Node Select crash"
    # Verify that opening AddNodeDialog with an invalid parent UUID does NOT crash the dialog
    node_repo = NodeRepository(session)
    node_service = NodeService(node_repo)
    invalid_parent_id = uuid.uuid4()

    from pathtree.ui.app import PathTreeApp
    from pathtree.ui.dialogs.add_node import AddNodeDialog

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        # Push the AddNodeDialog with invalid parent ID
        dialog = AddNodeDialog(
            node_service=node_service, default_parent_id=invalid_parent_id
        )
        await app.push_screen(dialog)
        await pilot.pause(0.01)

        # The screen should be active and focused without crashing
        assert isinstance(app.screen, AddNodeDialog)

        # Close the dialog
        await pilot.press("escape")
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_edit_profile_dialog_regression(session):
    # Regression test for "EditProfileDialog Select crash"
    # Verify that opening EditProfileDialog with a deleted/invalid working directory ID does NOT crash the dialog
    node_repo = NodeRepository(session)
    node_service = NodeService(node_repo)
    ws = node_service.create_node(name="WS", node_kind="workspace")
    script = node_service.create_node(
        name="Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=__file__,
    )

    lp_repo = LaunchProfileRepository(session)
    lp_service = LaunchProfileService(node_service, lp_repo)

    # Create a profile referencing a working directory that does not exist or has been deleted
    invalid_wd_id = uuid.uuid4()
    profile = lp_service.create_profile(
        name="Bad WD Prof",
        target_node_id=script.id,
        arguments=[],
    )
    # Expunge the profile from the session to avoid SQLModel/SQLAlchemy autoflush when querying nodes
    session.expunge(profile)
    # Manually set the working directory node ID to an invalid UUID on the transient in-memory object
    profile.working_directory_node_id = invalid_wd_id

    from pathtree.ui.app import PathTreeApp
    from pathtree.ui.dialogs.edit_profile import EditProfileDialog

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        # Mock get_profile to return our in-memory modified profile with the invalid WD
        with mock.patch.object(lp_service, "get_profile", return_value=profile):
            # Push the EditProfileDialog
            dialog = EditProfileDialog(
                node_service=node_service,
                launch_profile_service=lp_service,
                profile_id=profile.id,
            )
            await app.push_screen(dialog)
            await pilot.pause(0.01)

        # The screen should be active and focused without crashing
        assert isinstance(app.screen, EditProfileDialog)

        # Close the dialog
        await pilot.press("escape")
        await pilot.pause(0.01)
        assert app.screen.id == "main-screen"
