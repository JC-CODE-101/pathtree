import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from pathtree.actions import (
    FileActionProvider,
    ResourceActionContext,
    ResourceActionRegistry,
)
from pathtree.actions.base import ResourceActionResultTarget
from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import (
    InvalidParentKindError,
    NodeService,
    PathNotAFileError,
    PathNotFoundError,
)
from pathtree.utils.launcher import LaunchError, PlatformLauncher


def test_registry_resolves_file_action_provider():
    """7. Verify registry resolves FileActionProvider."""
    registry = ResourceActionRegistry()
    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)
    registry.register("resource", "file", provider)

    resolved = registry.get_provider("resource", "file")
    assert resolved is provider
    assert resolved.resource_type == "file"


def test_file_default_action_is_open_file():
    """8. Verify File default action is open_file."""
    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="testfile.txt",
        node_kind="resource",
        resource_type="file",
        path="/some/file.txt",
    )
    context = ResourceActionContext(node=node)

    default_act = provider.get_default_action(context)
    assert default_act is not None
    assert default_act.id == "open_file"
    assert default_act.is_default is True


def test_available_file_action_ids_are_stable():
    """9. Verify available action IDs are stable."""
    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="testfile.txt",
        node_kind="resource",
        resource_type="file",
        path="/some/file.txt",
    )
    context = ResourceActionContext(node=node)

    actions = provider.get_available_actions(context)
    action_ids = [a.id for a in actions]
    assert "open_file" in action_ids
    assert "edit_file" in action_ids
    assert "copy_path" in action_ids
    assert "view_details" in action_ids


@patch("subprocess.Popen")
def test_open_file_uses_argv_and_never_shell_true(mock_popen, tmp_path):
    """10. Verify open_file uses argv and never shell=True."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("hello")

    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.txt",
        node_kind="resource",
        resource_type="file",
        path=str(dummy_file),
    )
    context = ResourceActionContext(node=node, resolved_path=str(dummy_file))

    result = provider.execute("open_file", context)
    assert result.success is True

    # Check subprocess.Popen was called with shell=False and correct argv list
    assert mock_popen.called
    args, kwargs = mock_popen.call_args
    assert "shell" not in kwargs or kwargs["shell"] is False
    assert isinstance(args[0], list)


def test_open_file_keeps_pathtree_open(tmp_path):
    """11. Verify open_file keeps PathTree open (exit_app=False)."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("hello")

    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.txt",
        node_kind="resource",
        resource_type="file",
        path=str(dummy_file),
    )
    context = ResourceActionContext(node=node, resolved_path=str(dummy_file))

    with patch("subprocess.Popen"):
        result = provider.execute("open_file", context)
        assert result.success is True
        assert result.exit_app is False


def test_edit_file_fails_safely_when_no_editor_configured():
    """12. Verify edit_file fails safely when no editor is configured."""
    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.txt",
        node_kind="resource",
        resource_type="file",
        path="/some/file.txt",
    )
    context = ResourceActionContext(node=node, resolved_path="/some/file.txt")

    # Clear environment variables
    with patch.dict(os.environ, {}, clear=True):
        result = provider.execute("edit_file", context)
        assert result.success is False
        assert "No editor configured" in result.error_message


@patch("subprocess.Popen")
@patch("shutil.which")
def test_edit_file_uses_explicit_argv_when_configured(mock_which, mock_popen, tmp_path):
    """13. Verify edit_file uses explicit argv when configured."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.write_text("hello")

    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.txt",
        node_kind="resource",
        resource_type="file",
        path=str(dummy_file),
    )
    context = ResourceActionContext(node=node, resolved_path=str(dummy_file))

    mock_which.return_value = "/usr/bin/nano"

    # Set EDITOR
    with patch.dict(os.environ, {"EDITOR": "nano --some-flag"}, clear=True):
        result = provider.execute("edit_file", context)
        assert result.success is True

        # Check subprocess.Popen was called with list of args
        mock_popen.assert_called_once()
        args, _ = mock_popen.call_args
        assert args[0] == ["nano", "--some-flag", str(dummy_file)]


def test_copy_path_returns_absolute_file_path():
    """14. Verify copy_path returns absolute file path."""
    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test.txt",
        node_kind="resource",
        resource_type="file",
        path="/some/file.txt",
    )
    context = ResourceActionContext(node=node, resolved_path="/absolute/some/file.txt")

    result = provider.execute("copy_path", context)
    assert result.success is True
    assert result.target == ResourceActionResultTarget.DETAILS
    assert result.output_value == "Path: /absolute/some/file.txt"


def test_view_details_returns_size_and_extension_metadata(tmp_path):
    """15. Verify view_details returns size and extension metadata."""
    dummy_file = tmp_path / "test_notes.md"
    dummy_file.write_text("My important notes!")

    mock_service = MagicMock(spec=NodeService)
    provider = FileActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="test_notes.md",
        node_kind="resource",
        resource_type="file",
        path=str(dummy_file),
        description="Daily journal",
    )
    context = ResourceActionContext(node=node, resolved_path=str(dummy_file))

    result = provider.execute("view_details", context)
    assert result.success is True
    assert result.target == ResourceActionResultTarget.DETAILS
    assert "Name: test_notes.md" in result.output_value
    assert f"Path: {dummy_file}" in result.output_value
    assert "Size: 19 bytes" in result.output_value
    assert "Extension: .md" in result.output_value
    assert "Description: Daily journal" in result.output_value


def test_create_valid_file_resource(session: Session, tmp_path):
    """1. Verify creating a valid File resource."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.touch()

    repo = NodeRepository(session)
    service = NodeService(repo)

    # Need workspace first as parent
    ws = service.create_node(name="My Workspace", node_kind="workspace")

    # Create file under workspace
    file_node = service.create_node(
        name="Valid File",
        node_kind="resource",
        resource_type="file",
        parent_id=ws.id,
        path=str(dummy_file),
    )
    assert file_node.id is not None
    assert file_node.name == "Valid File"
    assert file_node.resource_type == "file"
    assert file_node.path == str(dummy_file.resolve())


def test_rejecting_missing_file_path(session: Session):
    """2. Verify rejecting a missing File path."""
    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="My Workspace", node_kind="workspace")

    # Path doesn't exist
    with pytest.raises(PathNotFoundError):
        service.create_node(
            name="Missing File",
            node_kind="resource",
            resource_type="file",
            parent_id=ws.id,
            path="/nonexistent/file/path.txt",
        )


def test_rejecting_directory_path_for_file(session: Session, tmp_path):
    """3. Verify rejecting a directory path for File."""
    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="My Workspace", node_kind="workspace")

    # Directory instead of file
    with pytest.raises(PathNotAFileError):
        service.create_node(
            name="Dir as File",
            node_kind="resource",
            resource_type="file",
            parent_id=ws.id,
            path=str(tmp_path),
        )


def test_file_may_be_placed_under_workspace(session: Session, tmp_path):
    """4. Verify File may be placed under Workspace."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.touch()

    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="Workspace Container", node_kind="workspace")
    file_node = service.create_node(
        name="File in WS",
        node_kind="resource",
        resource_type="file",
        parent_id=ws.id,
        path=str(dummy_file),
    )
    assert file_node.parent_id == ws.id


def test_file_may_be_placed_under_folder(session: Session, tmp_path):
    """5. Verify File may be placed under Folder."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.touch()

    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="WS", node_kind="workspace")
    folder = service.create_node(
        name="Folder Container", node_kind="folder", parent_id=ws.id
    )
    file_node = service.create_node(
        name="File in Folder",
        node_kind="resource",
        resource_type="file",
        parent_id=folder.id,
        path=str(dummy_file),
    )
    assert file_node.parent_id == folder.id


def test_file_may_not_have_children(session: Session, tmp_path):
    """6. Verify File may not have children."""
    dummy_file = tmp_path / "test.txt"
    dummy_file.touch()

    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="WS", node_kind="workspace")
    file_node = service.create_node(
        name="File Parent Candidate",
        node_kind="resource",
        resource_type="file",
        parent_id=ws.id,
        path=str(dummy_file),
    )

    with pytest.raises(InvalidParentKindError) as excinfo:
        service.create_node(
            name="Child node",
            node_kind="folder",
            parent_id=file_node.id,
        )
    assert "is not allowed" in str(excinfo.value)


@patch("sys.platform", "win32")
@patch("os.startfile", create=True)
def test_windows_uses_os_startfile_only(mock_startfile, tmp_path):
    """Verify that on Windows, PlatformLauncher uses os.startfile only."""
    dummy_file = tmp_path / "win_test.txt"
    dummy_file.touch()

    PlatformLauncher.open_path(str(dummy_file))
    mock_startfile.assert_called_once_with(str(dummy_file))


@patch("sys.platform", "win32")
@patch("os.startfile", create=True)
def test_windows_launch_error_on_startfile_failure(mock_startfile, tmp_path):
    """Verify that expected startfile failure raises LaunchError."""
    dummy_file = tmp_path / "win_fail.txt"
    dummy_file.touch()

    mock_startfile.side_effect = OSError("Access denied")

    with pytest.raises(LaunchError) as exc:
        PlatformLauncher.open_path(str(dummy_file))
    assert "Failed to open path" in str(exc.value)


@patch("sys.platform", "linux")
@patch("subprocess.Popen")
@patch("shutil.which")
def test_linux_uses_xdg_open(mock_which, mock_popen, tmp_path):
    """Verify that on Linux, PlatformLauncher uses xdg-open."""
    dummy_file = tmp_path / "linux_test.txt"
    dummy_file.touch()

    mock_which.return_value = "/usr/bin/xdg-open"

    PlatformLauncher.open_path(str(dummy_file))
    mock_popen.assert_called_once_with(["xdg-open", str(dummy_file)])
