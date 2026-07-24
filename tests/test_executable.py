import os
import sys
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from pathtree.actions import (
    ResourceActionContext,
    ResourceActionRegistry,
)
from pathtree.actions.base import ResourceActionResultTarget
from pathtree.actions.executable import ExecutableActionProvider
from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import (
    InvalidParentKindError,
    NodeService,
    PathNotAFileError,
    PathNotFoundError,
    ValidationError,
)
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.widgets.path_autocomplete import PathAutocompleteMode
from pathtree.utils.icons import NodeIconCatalog
from pathtree.utils.launcher import PlatformLauncher

# ==================== SERVICE & HIERARCHY TESTS ====================


def test_executable_node_creation_and_hierarchy(session: Session, tmp_path):
    """Verify Executable resource creation, placement and root rejection."""
    dummy_exec = tmp_path / "app.exe" if sys.platform == "win32" else tmp_path / "app"
    dummy_exec.touch()
    if sys.platform != "win32":
        os.chmod(dummy_exec, 0o755)

    repo = NodeRepository(session)
    service = NodeService(repo)

    # 1. Create under Workspace
    ws = service.create_node(name="Workspace Container", node_kind="workspace")
    exec_node = service.create_node(
        name="Test Exec",
        node_kind="resource",
        resource_type="executable",
        parent_id=ws.id,
        path=str(dummy_exec),
    )
    assert exec_node.id is not None
    assert exec_node.resource_type == "executable"
    assert exec_node.path == str(dummy_exec.resolve())

    # 2. Create under Folder
    folder = service.create_node(name="Sub Folder", node_kind="folder", parent_id=ws.id)
    exec_node_2 = service.create_node(
        name="Test Exec 2",
        node_kind="resource",
        resource_type="executable",
        parent_id=folder.id,
        path=str(dummy_exec),
    )
    assert exec_node_2.parent_id == folder.id

    # 3. Cannot create under root
    with pytest.raises(ValidationError) as exc:
        service.create_node(
            name="Exec Root",
            node_kind="resource",
            resource_type="executable",
            parent_id=None,
            path=str(dummy_exec),
        )
    assert "cannot be created under Root" in str(exc.value)


def test_executable_cannot_parent_node(session: Session, tmp_path):
    """Verify Executable cannot parent another node."""
    dummy_exec = tmp_path / "app.exe" if sys.platform == "win32" else tmp_path / "app"
    dummy_exec.touch()
    if sys.platform != "win32":
        os.chmod(dummy_exec, 0o755)

    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="WS", node_kind="workspace")
    exec_node = service.create_node(
        name="Exec Parent",
        node_kind="resource",
        resource_type="executable",
        parent_id=ws.id,
        path=str(dummy_exec),
    )

    with pytest.raises(InvalidParentKindError):
        service.create_node(
            name="Child",
            node_kind="folder",
            parent_id=exec_node.id,
        )


def test_executable_path_validation(session: Session, tmp_path):
    """Verify Executable path validation rules: present, exists, not a directory."""
    repo = NodeRepository(session)
    service = NodeService(repo)
    ws = service.create_node(name="WS", node_kind="workspace")

    # Missing is rejected
    with pytest.raises(ValidationError) as exc:
        service.create_node(
            name="Missing Path",
            node_kind="resource",
            resource_type="executable",
            parent_id=ws.id,
            path="",
        )
    assert "path cannot be empty" in str(exc.value)

    # Nonexistent path is rejected
    with pytest.raises(PathNotFoundError) as exc:
        service.create_node(
            name="Nonexistent",
            node_kind="resource",
            resource_type="executable",
            parent_id=ws.id,
            path=str(tmp_path / "nonexistent_binary"),
        )
    assert "does not exist" in str(exc.value)

    # Directory is rejected
    with pytest.raises(PathNotAFileError) as exc:
        service.create_node(
            name="Dir as Exec",
            node_kind="resource",
            resource_type="executable",
            parent_id=ws.id,
            path=str(tmp_path),
        )
    assert "is not a regular file" in str(exc.value)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="POSIX execution checks require non-Windows platform",
)
def test_executable_posix_permission_validation(session: Session, tmp_path):
    """Verify missing POSIX executable permission is rejected on Unix."""
    repo = NodeRepository(session)
    service = NodeService(repo)
    ws = service.create_node(name="WS", node_kind="workspace")

    # Regular file without execute permission
    non_exec = tmp_path / "non_exec_file"
    non_exec.touch()
    os.chmod(non_exec, 0o644)  # readable, not executable

    with pytest.raises(ValidationError) as exc:
        service.create_node(
            name="No Permission",
            node_kind="resource",
            resource_type="executable",
            parent_id=ws.id,
            path=str(non_exec),
        )
    assert "permission is missing" in str(exc.value)


@pytest.mark.skipif(
    sys.platform != "win32", reason="Windows executable checks require Windows platform"
)
def test_executable_windows_extension_validation(session: Session, tmp_path):
    """Verify Windows executable extensions are validated correctly on Windows."""
    repo = NodeRepository(session)
    service = NodeService(repo)
    ws = service.create_node(name="WS", node_kind="workspace")

    # Correct extension
    correct_exe = tmp_path / "valid.exe"
    correct_exe.touch()
    node = service.create_node(
        name="Valid Windows Executable",
        node_kind="resource",
        resource_type="executable",
        parent_id=ws.id,
        path=str(correct_exe),
    )
    assert node.id is not None

    correct_com = tmp_path / "valid.com"
    correct_com.touch()
    node_com = service.create_node(
        name="Valid COM Executable",
        node_kind="resource",
        resource_type="executable",
        parent_id=ws.id,
        path=str(correct_com),
    )
    assert node_com.id is not None

    # Incorrect extension
    invalid_ext = tmp_path / "app.txt"
    invalid_ext.touch()
    with pytest.raises(ValidationError) as exc:
        service.create_node(
            name="Invalid Extension",
            node_kind="resource",
            resource_type="executable",
            parent_id=ws.id,
            path=str(invalid_ext),
        )
    assert "not a valid Windows executable" in str(exc.value)


# ==================== PROVIDER & ACTIONS TESTS ====================


def test_executable_provider_is_registered():
    """Verify ExecutableActionProvider is registered with registry."""
    registry = ResourceActionRegistry()
    mock_service = MagicMock(spec=NodeService)
    provider = ExecutableActionProvider(mock_service)
    registry.register("resource", "executable", provider)

    resolved = registry.get_provider("resource", "executable")
    assert resolved is provider
    assert resolved.resource_type == "executable"


def test_launch_is_default_action():
    """Verify Launch is the default action."""
    mock_service = MagicMock(spec=NodeService)
    provider = ExecutableActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="my_app",
        node_kind="resource",
        resource_type="executable",
        path="/bin/my_app",
    )
    context = ResourceActionContext(node=node)

    default_act = provider.get_default_action(context)
    assert default_act is not None
    assert default_act.id == "launch"
    assert default_act.is_default is True


@patch("subprocess.Popen")
@patch("shutil.which")
def test_executable_launch_behavior(mock_which, mock_popen, tmp_path):
    """Verify Launch action runs with secure sequential argv and parent cwd."""
    mock_which.return_value = "/bin/app"
    my_app = tmp_path / "app"
    my_app.touch()

    # Stub validation and resolved path
    mock_service = MagicMock(spec=NodeService)
    mock_service.resolve_node_path.return_value = my_app

    provider = ExecutableActionProvider(mock_service)
    node = Node(
        id=uuid.uuid4(),
        name="my_app",
        node_kind="resource",
        resource_type="executable",
        path=str(my_app),
    )
    context = ResourceActionContext(node=node, resolved_path=str(my_app))

    result = provider.execute("launch", context)
    assert result.success is True
    assert "Launched executable" in result.message

    # Assert subprocess.Popen arguments
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert args[0] == [str(my_app)]
    assert kwargs.get("cwd") == my_app.parent


@patch("pathtree.utils.launcher.PlatformLauncher.open_path")
def test_executable_open_containing_folder(mock_open_path, tmp_path):
    """Verify Open Containing Folder action opens the parent directory."""
    my_app = tmp_path / "app"
    my_app.touch()

    mock_service = MagicMock(spec=NodeService)
    mock_service.resolve_node_path.return_value = my_app

    provider = ExecutableActionProvider(mock_service)
    node = Node(
        id=uuid.uuid4(),
        name="my_app",
        node_kind="resource",
        resource_type="executable",
        path=str(my_app),
    )
    context = ResourceActionContext(node=node, resolved_path=str(my_app))

    result = provider.execute("open_containing_folder", context)
    assert result.success is True
    assert "Opened containing folder" in result.message
    mock_open_path.assert_called_once_with(str(my_app.parent.absolute()))


@patch("subprocess.run")
@patch("shutil.which")
@patch("sys.platform", "darwin")
def test_platform_launcher_copy_to_clipboard_macos(mock_which, mock_run):
    """Verify copy_to_clipboard on macOS uses pbcopy securely without shell."""
    mock_which.return_value = "/usr/bin/pbcopy"
    PlatformLauncher.copy_to_clipboard("test text")

    mock_run.assert_called_once_with(
        ["pbcopy"], input="test text", text=True, check=True, shell=False
    )


@patch("subprocess.run")
@patch("shutil.which")
@patch("sys.platform", "linux")
def test_platform_launcher_copy_to_clipboard_linux_wl_copy(mock_which, mock_run):
    """Verify copy_to_clipboard on Linux uses wl-copy when available."""
    mock_which.side_effect = lambda cmd: (
        "/usr/bin/wl-copy" if cmd == "wl-copy" else None
    )
    PlatformLauncher.copy_to_clipboard("test text")

    mock_run.assert_called_once_with(
        ["wl-copy"], input="test text", text=True, check=True, shell=False
    )


@patch("shutil.which", return_value=None)
@patch("sys.platform", "linux")
def test_platform_launcher_copy_to_clipboard_linux_no_backend(mock_which):
    """Verify copy_to_clipboard on Linux raises LaunchError if no backends exist."""
    from pathtree.utils.launcher import LaunchError

    with pytest.raises(LaunchError) as exc:
        PlatformLauncher.copy_to_clipboard("test text")
    assert "No supported clipboard mechanism is available" in str(exc.value)


@patch("pathtree.utils.launcher.PlatformLauncher.copy_to_clipboard")
def test_executable_copy_path_success(mock_copy, tmp_path):
    """Verify Copy Path action success with spaces in path."""
    mock_service = MagicMock(spec=NodeService)
    provider = ExecutableActionProvider(mock_service)

    path_with_spaces = "/bin/my path with spaces"
    node = Node(
        id=uuid.uuid4(),
        name="my_app",
        node_kind="resource",
        resource_type="executable",
        path=path_with_spaces,
    )
    context = ResourceActionContext(node=node, resolved_path=path_with_spaces)

    result = provider.execute("copy_path", context)
    assert result.success is True
    assert result.message == f"Copied path to clipboard: {path_with_spaces}"
    mock_copy.assert_called_once_with(path_with_spaces)


@patch("pathtree.utils.launcher.PlatformLauncher.copy_to_clipboard")
def test_executable_copy_path_failure(mock_copy, tmp_path):
    """Verify Copy Path failure handles error gracefully with no false success."""
    from pathtree.utils.launcher import LaunchError

    mock_copy.side_effect = LaunchError("No clipboard available.")

    mock_service = MagicMock(spec=NodeService)
    provider = ExecutableActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="my_app",
        node_kind="resource",
        resource_type="executable",
        path="/bin/my_app",
    )
    context = ResourceActionContext(node=node, resolved_path="/bin/my_app")

    result = provider.execute("copy_path", context)
    assert result.success is False
    assert result.message is None  # no false success message
    assert "Clipboard error" in result.error_message


@patch("pathtree.utils.launcher.PlatformLauncher.copy_to_clipboard")
def test_consistent_copy_path_across_providers(mock_copy):
    """Verify all resource providers copy path to clipboard consistently."""
    from pathtree.actions.directory import DirectoryActionProvider
    from pathtree.actions.executable import ExecutableActionProvider
    from pathtree.actions.file import FileActionProvider
    from pathtree.actions.script import ScriptActionProvider

    mock_service = MagicMock(spec=NodeService)
    node_id = uuid.uuid4()

    # 1. Directory
    dir_node = Node(
        id=node_id,
        name="dir",
        node_kind="resource",
        resource_type="directory",
        path="/dir",
    )
    dir_provider = DirectoryActionProvider(mock_service)
    res = dir_provider.execute(
        "copy_path", ResourceActionContext(node=dir_node, resolved_path="/dir")
    )
    assert res.success is True
    assert res.message == "Copied path to clipboard: /dir"

    # 2. File
    file_node = Node(
        id=node_id,
        name="file",
        node_kind="resource",
        resource_type="file",
        path="/file",
    )
    file_provider = FileActionProvider(mock_service)
    res = file_provider.execute(
        "copy_path", ResourceActionContext(node=file_node, resolved_path="/file")
    )
    assert res.success is True
    assert res.message == "Copied path to clipboard: /file"

    # 3. Script
    script_node = Node(
        id=node_id,
        name="script",
        node_kind="resource",
        resource_type="script",
        path="/script",
    )
    script_provider = ScriptActionProvider(mock_service)
    res = script_provider.execute(
        "copy_path", ResourceActionContext(node=script_node, resolved_path="/script")
    )
    assert res.success is True
    assert res.message == "Copied path to clipboard: /script"

    # 4. Executable
    exec_node = Node(
        id=node_id,
        name="exec",
        node_kind="resource",
        resource_type="executable",
        path="/exec",
    )
    exec_provider = ExecutableActionProvider(mock_service)
    res = exec_provider.execute(
        "copy_path", ResourceActionContext(node=exec_node, resolved_path="/exec")
    )
    assert res.success is True
    assert res.message == "Copied path to clipboard: /exec"

    # Ensure clipboard utility was called for all of them
    assert mock_copy.call_count == 4


@patch("subprocess.Popen")
def test_executable_view_details_no_execution(mock_popen, tmp_path):
    """Verify View Details reports metadata without executing the binary."""
    my_app = tmp_path / "app"
    my_app.touch()

    mock_service = MagicMock(spec=NodeService)
    mock_service.resolve_node_path.return_value = my_app

    provider = ExecutableActionProvider(mock_service)
    node = Node(
        id=uuid.uuid4(),
        name="my_app",
        node_kind="resource",
        resource_type="executable",
        path=str(my_app),
        description="Core utility binary",
    )
    context = ResourceActionContext(node=node, resolved_path=str(my_app))

    result = provider.execute("view_details", context)
    assert result.success is True
    assert result.target == ResourceActionResultTarget.DETAILS

    details = result.output_value
    assert "Name: my_app" in details
    assert "Resource Type: executable" in details
    assert f"Full Path: {my_app}" in details
    assert "Description: Core utility binary" in details

    mock_popen.assert_not_called()


# ==================== UI & DIALOG INTEGRATION TESTS ====================


def test_add_dialog_exposes_executable(session: Session):
    """Verify Add Node dialog exposes Executable resource type."""
    repo = NodeRepository(session)
    service = NodeService(repo)
    ws = service.create_node(name="WS", node_kind="workspace")

    dialog = AddNodeDialog(service, default_parent_id=ws.id)

    # Mock all child widget queries to prevent NoMatches on unmounted dialog
    mock_widgets = MagicMock()
    dialog.query_one = MagicMock(return_value=mock_widgets)

    from textual.widgets import RadioButton, RadioSet

    mock_radio = MagicMock(spec=RadioButton)
    mock_radio.id = "radio-executable"
    event = RadioSet.Changed(RadioSet(), mock_radio)
    dialog.on_radio_set_changed(event)

    assert dialog.selected_type == "executable"

    mock_widgets.set_node_type.assert_called_with("resource", "executable")
    mock_widgets.set_mode.assert_called_with(PathAutocompleteMode.EXECUTABLE)


def test_edit_dialog_initializes_executable(session: Session, tmp_path):
    """Verify Edit Node dialog initializes Executable correctly."""
    repo = NodeRepository(session)
    service = NodeService(repo)
    ws = service.create_node(name="WS", node_kind="workspace")

    dummy_exec = tmp_path / "app.exe" if sys.platform == "win32" else tmp_path / "app"
    dummy_exec.touch()
    if sys.platform != "win32":
        os.chmod(dummy_exec, 0o755)

    node = service.create_node(
        name="Exec Node",
        node_kind="resource",
        resource_type="executable",
        parent_id=ws.id,
        path=str(dummy_exec),
    )

    dialog = EditNodeDialog(service, node.id)
    assert dialog.node.id == node.id
    assert dialog.node.resource_type == "executable"


def test_default_executable_icon_resolution():
    """Verify Executable resource icon resolution."""
    catalog = NodeIconCatalog()
    icon = catalog.get_default_icon("resource", "executable")
    assert icon == "⚙"

    # Verify customized option list is returned correctly
    recs = catalog.get_recommended_icons("resource", "executable")
    assert len(recs) > 0
    assert any(rec.symbol == "⚙" for rec in recs)


# ==================== PATH AUTOCOMPLETE TESTS ====================


def test_path_autocomplete_executable_mode(tmp_path):
    """Verify PathAutocomplete executable mode file list filtering."""
    # 1. Create a dummy directory with several file types
    d = tmp_path / "bin"
    d.mkdir()

    # Directory
    sub = d / "subdir"
    sub.mkdir()

    # Executable file
    exe_file = d / "app.exe"
    exe_file.touch()

    # Non-executable file
    text_file = d / "notes.txt"
    text_file.touch()

    # Extensionless file
    extless_file = d / "readme"
    extless_file.touch()

    from pathtree.ui.widgets.path_autocomplete import PathAutocomplete

    # Initialize PathAutocomplete in EXECUTABLE mode
    autocomplete = PathAutocomplete(mode=PathAutocompleteMode.EXECUTABLE)

    # Patch os.path internally to look at our created temp path
    with (
        patch("os.path.exists", return_value=True),
        patch("os.path.isdir", return_value=True),
    ):
        # We'll mock the scandir to return entries we expect
        class MockEntry:
            def __init__(self, name, is_dir, is_file):
                self.name = name
                self._is_dir = is_dir
                self._is_file = is_file

            def is_dir(self, follow_symlinks=True):
                return self._is_dir

            def is_file(self, follow_symlinks=True):
                return self._is_file

        mock_entries = [
            MockEntry("subdir", True, False),
            MockEntry("app.exe", False, True),
            MockEntry("app.com", False, True),
            MockEntry("notes.txt", False, True),
            MockEntry("readme", False, True),
        ]

        def mock_access(path, mode):
            # mock X_OK access: only subdir or app.exe is executable on POSIX
            path_str = str(path)
            return path_str.endswith("app.exe") or "subdir" in path_str

        with (
            patch("os.scandir") as mock_scandir,
            patch("os.access", side_effect=mock_access),
        ):
            mock_scandir.return_value.__enter__.return_value = iter(mock_entries)

            # Run suggestion update
            autocomplete.update_suggestions("bin/")

            # Get suggestions from the OptionList
            options = [
                autocomplete.option_list.get_option_at_index(i).prompt
                for i in range(autocomplete.option_list.option_count)
            ]

            # Subdir/ should be present (directory navigation is allowed)
            assert "subdir/" in options

            if sys.platform != "win32":
                # On POSIX: "app.exe" is shown based on execute permission.
                # Extensionless is supported on POSIX if X_OK is mocked to return True.
                assert "app.exe" in options
                assert "notes.txt" not in options
                assert "readme" not in options
            else:
                # On Windows: only .exe and .com are allowed.
                # Extensionless is strictly excluded.
                assert "app.exe" in options
                assert "app.com" in options
                assert "notes.txt" not in options
                assert "readme" not in options


def test_executable_autocomplete_validation_consistency(tmp_path):
    """Test consistency between autocomplete rules and NodeService validation."""
    from pathtree.utils.path import is_launchable_file

    exe_file = tmp_path / "test.exe"
    com_file = tmp_path / "test.com"
    txt_file = tmp_path / "test.txt"
    no_ext_file = tmp_path / "test_no_ext"

    exe_file.touch()
    com_file.touch()
    txt_file.touch()
    no_ext_file.touch()

    if sys.platform == "win32":
        assert is_launchable_file(exe_file) is True
        assert is_launchable_file(com_file) is True
        assert is_launchable_file(txt_file) is False
        assert is_launchable_file(no_ext_file) is False
    else:
        # On POSIX, no execute permissions yet
        assert is_launchable_file(exe_file) is False

        # Grant execute permissions
        os.chmod(exe_file, 0o755)
        os.chmod(no_ext_file, 0o755)
        assert is_launchable_file(exe_file) is True
        assert (
            is_launchable_file(no_ext_file) is True
        )  # extensionless POSIX exec supported
        assert is_launchable_file(txt_file) is False
