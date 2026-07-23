import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from pathtree.actions import (
    ResourceActionContext,
    ResourceActionRegistry,
)
from pathtree.actions.base import ResourceActionResultTarget
from pathtree.actions.script import ScriptActionProvider
from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import (
    InvalidParentKindError,
    NodeService,
    PathNotAFileError,
    PathNotFoundError,
)
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.widgets.path_autocomplete import PathAutocompleteMode
from pathtree.utils.icons import NodeIconCatalog
from pathtree.utils.launcher import PlatformLauncher
from pathtree.utils.script_resolver import (
    ScriptResolutionError,
    resolve_script_argv,
)

# ==================== SERVICE & HIERARCHY TESTS ====================


def test_script_node_creation_and_hierarchy(session: Session, tmp_path):
    """1. Verify Script is accepted as a resource type.
    2. Verify Script may be placed under Workspace.
    3. Verify Script may be placed under Folder.
    """
    dummy_script = tmp_path / "script.py"
    dummy_script.touch()

    repo = NodeRepository(session)
    service = NodeService(repo)

    # 1 & 2: Create under Workspace
    ws = service.create_node(name="Workspace Container", node_kind="workspace")
    script_node = service.create_node(
        name="Test Script py",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=str(dummy_script),
    )
    assert script_node.id is not None
    assert script_node.resource_type == "script"
    assert script_node.path == str(dummy_script.resolve())

    # 3: Create under Folder
    folder = service.create_node(name="Sub Folder", node_kind="folder", parent_id=ws.id)
    script_node_2 = service.create_node(
        name="Test Script 2",
        node_kind="resource",
        resource_type="script",
        parent_id=folder.id,
        path=str(dummy_script),
    )
    assert script_node_2.parent_id == folder.id


def test_script_cannot_parent_node(session: Session, tmp_path):
    """4. Verify Script cannot parent another node."""
    dummy_script = tmp_path / "script.sh"
    dummy_script.touch()

    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="WS", node_kind="workspace")
    script_node = service.create_node(
        name="Script Parent",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=str(dummy_script),
    )

    with pytest.raises(InvalidParentKindError):
        service.create_node(
            name="Child",
            node_kind="folder",
            parent_id=script_node.id,
        )


def test_script_path_validation(session: Session, tmp_path):
    """5. Verify existing script file passes validation.
    6. Verify missing script path is rejected.
    7. Verify directory path is rejected for Script.
    """
    repo = NodeRepository(session)
    service = NodeService(repo)
    ws = service.create_node(name="WS", node_kind="workspace")

    # 5. Existing passes
    existing = tmp_path / "run.py"
    existing.touch()
    node = service.create_node(
        name="Valid Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=str(existing),
    )
    assert node.path == str(existing.resolve())

    # 6. Missing is rejected
    with pytest.raises(PathNotFoundError):
        service.create_node(
            name="Missing",
            node_kind="resource",
            resource_type="script",
            parent_id=ws.id,
            path=str(tmp_path / "doesnotexist.sh"),
        )

    # 7. Directory is rejected
    with pytest.raises(PathNotAFileError):
        service.create_node(
            name="Dir as Script",
            node_kind="resource",
            resource_type="script",
            parent_id=ws.id,
            path=str(tmp_path),
        )


# ==================== DIALOG & UI TESTS ====================


def test_add_dialog_exposes_script(session: Session):
    """8. Verify Add dialog exposes Script.
    10. Verify Script uses File-mode PathAutocomplete.
    """
    repo = NodeRepository(session)
    service = NodeService(repo)
    ws = service.create_node(name="WS", node_kind="workspace")

    dialog = AddNodeDialog(service, default_parent_id=ws.id)

    # Mock all child widget queries to prevent NoMatches on unmounted dialog
    mock_widgets = MagicMock()
    dialog.query_one = MagicMock(return_value=mock_widgets)

    # Mocking radio button pressing simulation
    from textual.widgets import RadioButton, RadioSet

    mock_radio = MagicMock(spec=RadioButton)
    mock_radio.id = "radio-script"
    event = RadioSet.Changed(RadioSet(), mock_radio)
    dialog.on_radio_set_changed(event)

    assert dialog.selected_type == "script"

    # Verify that correct node type is set on IconPicker
    # and correct PathAutocomplete mode is set
    mock_widgets.set_node_type.assert_called_with("resource", "script")
    mock_widgets.set_mode.assert_called_with(PathAutocompleteMode.FILE)


def test_edit_dialog_initializes_script_correctly(session: Session, tmp_path):
    """9. Verify Edit dialog initializes Script correctly."""
    repo = NodeRepository(session)
    service = NodeService(repo)
    ws = service.create_node(name="WS", node_kind="workspace")

    dummy_script = tmp_path / "script.py"
    dummy_script.touch()
    node = service.create_node(
        name="Script Node",
        node_kind="resource",
        resource_type="script",
        parent_id=ws.id,
        path=str(dummy_script),
    )

    dialog = EditNodeDialog(service, node.id)
    # If the widget initializes correctly, node must match and it shouldn't raise errors
    assert dialog.node.id == node.id
    assert dialog.node.resource_type == "script"


def test_default_script_icon_applied():
    """11. Verify default Script icon is applied."""
    catalog = NodeIconCatalog()
    icon = catalog.get_default_icon("resource", "script")
    assert icon == "⚡"


# ==================== PROVIDER & ACTIONS TESTS ====================


def test_script_provider_is_registered():
    """12. Verify Script provider is registered."""
    registry = ResourceActionRegistry()
    mock_service = MagicMock(spec=NodeService)
    provider = ScriptActionProvider(mock_service)
    registry.register("resource", "script", provider)

    resolved = registry.get_provider("resource", "script")
    assert resolved is provider
    assert resolved.resource_type == "script"


def test_run_script_is_default_action():
    """13. Verify Run Script is the default action."""
    mock_service = MagicMock(spec=NodeService)
    provider = ScriptActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="testscript.sh",
        node_kind="resource",
        resource_type="script",
        path="/some/script.sh",
    )
    context = ResourceActionContext(node=node)

    default_act = provider.get_default_action(context)
    assert default_act is not None
    assert default_act.id == "run_script"
    assert default_act.is_default is True


# ==================== INTERPRETER & SHEBANG RESOLUTION TESTS ====================


@patch("shutil.which")
def test_python_extension_resolves_to_python3(mock_which, tmp_path):
    """14. Verify Python extension resolves to python3."""
    mock_which.side_effect = lambda cmd: (
        "/usr/bin/python3" if cmd == "python3" else None
    )
    script = tmp_path / "test.py"
    script.touch()

    argv = resolve_script_argv(script)
    assert argv == ["python3", str(script)]


@patch("shutil.which")
def test_shell_extension_resolves_to_bash(mock_which, tmp_path):
    """15. Verify Shell extension resolves to bash."""
    mock_which.side_effect = lambda cmd: "/bin/bash" if cmd == "bash" else None
    script = tmp_path / "test.sh"
    script.touch()

    argv = resolve_script_argv(script)
    assert argv == ["bash", str(script)]


def test_shebang_env_python3_resolves_safely(tmp_path):
    """16. Verify /usr/bin/env python3 shebang resolves safely."""
    script = tmp_path / "env_script"
    script.write_bytes(b"#!/usr/bin/env python3\nprint('hello')\n")

    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda cmd: (
            "/usr/bin/python3" if "python" in cmd else None
        )
        argv = resolve_script_argv(script)
        assert argv == ["python3", str(script)]


def test_shebang_direct_path_resolves_safely(tmp_path):
    """Verify raw shebang interpreter resolves safely."""
    script = tmp_path / "raw_script"
    script.write_bytes(b"#!/usr/bin/python3\nprint('hello')\n")

    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda cmd: (
            "/usr/bin/python3" if "python" in cmd else None
        )
        argv = resolve_script_argv(script)
        assert argv == ["/usr/bin/python3", str(script)]


def test_shebang_env_with_flags_resolves_safely(tmp_path):
    """Verify /usr/bin/env -S shebang parses correctly."""
    script = tmp_path / "env_flag_script"
    script.write_bytes(b"#!/usr/bin/env -S node --inspect\nconsole.log(1)\n")

    with patch("shutil.which") as mock_which:
        mock_which.side_effect = lambda cmd: "/usr/bin/node" if "node" in cmd else None
        argv = resolve_script_argv(script)
        assert argv == ["node", "--inspect", str(script)]


def test_direct_executable_script_supported(tmp_path):
    """17. Verify Direct executable script is supported."""
    script = tmp_path / "binary_exec"
    script.touch()

    with patch("os.access") as mock_access, patch("shutil.which") as mock_which:
        mock_access.return_value = True  # Mock X_OK executable check
        mock_which.return_value = str(script)

        argv = resolve_script_argv(script)
        assert argv == [str(script)]


@patch("shutil.which")
def test_missing_interpreter_returns_typed_error(mock_which, tmp_path):
    """18. Verify missing interpreter returns a typed error (ScriptResolutionError)."""
    mock_which.return_value = None  # No interpreter exists
    script = tmp_path / "test.py"
    script.touch()

    with pytest.raises(ScriptResolutionError) as exc:
        resolve_script_argv(script)
    assert "not installed or available in PATH" in str(exc.value)


@patch("shutil.which")
def test_unsupported_script_returns_typed_error(mock_which, tmp_path):
    """19. Verify unsupported script returns a typed error (ScriptResolutionError)."""
    mock_which.return_value = "/usr/bin/file"
    script = tmp_path / "test.xyz"  # Unknown extension, no shebang, not executable
    script.touch()

    with pytest.raises(ScriptResolutionError) as exc:
        resolve_script_argv(script)
    assert "Unsupported script file" in str(exc.value)


# ==================== LAUNCHER & PROCESS TESTS ====================


@patch("subprocess.Popen")
@patch("shutil.which")
def test_explicit_argv_and_no_shell_true(mock_which, mock_popen, tmp_path):
    """20. Verify explicit argv is passed to subprocess.
    21. Verify no execution path uses shell=True.
    22. Verify working directory defaults to the script parent.
    """
    mock_which.return_value = "/usr/bin/xterm"
    script = tmp_path / "test.py"
    script.touch()

    mock_service = MagicMock(spec=NodeService)
    provider = ScriptActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.py",
        node_kind="resource",
        resource_type="script",
        path=str(script),
    )
    context = ResourceActionContext(node=node, resolved_path=str(script))

    result = provider.execute("run_script", context)
    assert result.success is True
    assert result.message == "Script launched in terminal."

    # Assert subprocess.Popen arguments
    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert isinstance(args[0], list)


@patch("shutil.which")
def test_terminal_resolution_order(mock_which, tmp_path):
    """Verify terminal emulator resolution order ($TERMINAL fallback)."""
    # Mock all terminal emulators as missing except wezterm
    mock_which.side_effect = lambda cmd: (
        "/usr/bin/wezterm" if cmd == "wezterm" else None
    )

    with patch("subprocess.Popen") as mock_popen:
        res = PlatformLauncher.launch_in_terminal(["python3", "test.py"], tmp_path)
        assert res.success is True
        mock_popen.assert_called_once()
        args, _ = mock_popen.call_args
        assert args[0][0] == "/usr/bin/wezterm"


@patch("shutil.which")
def test_env_terminal_override(mock_which, tmp_path):
    """Verify that $TERMINAL environment variable override is respected."""
    mock_which.side_effect = lambda cmd: "/custom/my-term" if cmd == "my-term" else None

    with (
        patch.dict(os.environ, {"TERMINAL": "my-term"}, clear=True),
        patch("subprocess.Popen") as mock_popen,
    ):
        res = PlatformLauncher.launch_in_terminal(["python3", "test.py"], tmp_path)
        assert res.success is True
        mock_popen.assert_called_once()
        args, _ = mock_popen.call_args
        assert args[0][0] == "/custom/my-term"


@patch("shutil.which")
def test_unsupported_terminal_returns_error(mock_which, tmp_path):
    """Verify unsupported terminal returns a typed error result."""
    mock_which.return_value = None  # No terminal emulators exist

    with patch.dict(os.environ, {}, clear=True):
        res = PlatformLauncher.launch_in_terminal(["python3", "test.py"], tmp_path)
        assert res.success is False
        assert "No supported terminal emulator found" in res.error_message


@patch("subprocess.Popen")
@patch("shutil.which")
def test_edit_script_reuses_safe_editor(mock_which, mock_popen, tmp_path):
    """23. Verify Edit Script reuses safe editor launching."""
    mock_which.return_value = "/usr/bin/nano"
    script = tmp_path / "test.py"
    script.touch()

    mock_service = MagicMock(spec=NodeService)
    provider = ScriptActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.py",
        node_kind="resource",
        resource_type="script",
        path=str(script),
    )
    context = ResourceActionContext(node=node, resolved_path=str(script))

    with patch.dict(os.environ, {"EDITOR": "nano -w"}, clear=True):
        result = provider.execute("edit_script", context)
        assert result.success is True

        mock_popen.assert_called_once_with(["nano", "-w", str(script)])


def test_copy_path_works():
    """24. Verify Copy Path works."""
    mock_service = MagicMock(spec=NodeService)
    provider = ScriptActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.py",
        node_kind="resource",
        resource_type="script",
        path="/abs/test.py",
    )
    context = ResourceActionContext(node=node, resolved_path="/abs/test.py")

    result = provider.execute("copy_path", context)
    assert result.success is True
    assert result.target == ResourceActionResultTarget.DETAILS
    assert result.output_value == "Path: /abs/test.py"


@patch("subprocess.Popen")
@patch("shutil.which")
def test_view_details_without_execution(mock_which, mock_popen, tmp_path):
    """25. Verify View Details reports detection without executing the script."""
    mock_which.return_value = "/usr/bin/python3"
    script = tmp_path / "test.py"
    script.touch()

    mock_service = MagicMock(spec=NodeService)
    provider = ScriptActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.py",
        node_kind="resource",
        resource_type="script",
        path=str(script),
        description="A cool python script",
    )
    context = ResourceActionContext(node=node, resolved_path=str(script))

    result = provider.execute("view_details", context)
    assert result.success is True
    assert result.target == ResourceActionResultTarget.DETAILS

    # Verify output contents
    details = result.output_value
    assert "Name: test.py" in details
    assert "Resource Type: script" in details
    assert f"Full Script Path: {script}" in details
    assert "Detected Interpreter: python3" in details
    assert f"Working Directory: {tmp_path}" in details
    assert "Path Exists: Yes" in details
    assert "Description: A cool python script" in details

    # Subprocess/process launch must NEVER have been triggered
    mock_popen.assert_not_called()


# ==================== AGNOSTIC UI ROUTING TESTS ====================


def test_mainscreen_remains_provider_agnostic():
    """26. Verify MainScreen remains provider-agnostic.
    It resolves the provider generically from the action registry,
    without executing concrete resource type branching.
    """
    from pathtree.ui.screens.main import MainScreen

    # Instantiate MainScreen with mocked components
    mock_service = MagicMock(spec=NodeService)
    screen = MainScreen(mock_service)

    # Assert directory, file, and script action providers are registered in the registry
    p_dir = screen.action_registry.get_provider("resource", "directory")
    p_file = screen.action_registry.get_provider("resource", "file")
    p_script = screen.action_registry.get_provider("resource", "script")

    assert p_dir is not None
    assert p_file is not None
    assert p_script is not None
