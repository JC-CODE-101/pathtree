import uuid
from pathlib import Path
from unittest.mock import MagicMock

from pathtree.actions import (
    DirectoryActionProvider,
    ResourceActionContext,
    ResourceActionRegistry,
)
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService


def test_registry_resolves_provider_for_directory_resource():
    """Verify registry resolves DirectoryActionProvider for a directory resource."""
    registry = ResourceActionRegistry()
    mock_service = MagicMock(spec=NodeService)
    provider = DirectoryActionProvider(mock_service)
    registry.register("resource", "directory", provider)

    resolved = registry.get_provider("resource", "directory")
    assert resolved is provider
    assert resolved.resource_type == "directory"


def test_registry_returns_no_provider_for_workspace_and_folders():
    """Verify registry returns None for workspace and folder nodes."""
    registry = ResourceActionRegistry()
    mock_service = MagicMock(spec=NodeService)
    provider = DirectoryActionProvider(mock_service)
    registry.register("resource", "directory", provider)

    # Workspace & Folder should return None even if we register other things
    assert registry.get_provider("workspace", None) is None
    assert registry.get_provider("folder", None) is None


def test_unsupported_resource_types_fail_safely():
    """Verify registry returns None and handles unsupported types gracefully."""
    registry = ResourceActionRegistry()
    # Querying unsupported node kind or resource type returns None
    assert registry.get_provider("resource", "unknown_type") is None
    assert registry.get_provider("invalid_kind", "directory") is None


def test_directory_default_action_is_change_directory():
    """Verify the default action of DirectoryActionProvider is change_directory."""
    mock_service = MagicMock(spec=NodeService)
    provider = DirectoryActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="testdir",
        node_kind="resource",
        resource_type="directory",
        path="/some/path",
    )
    context = ResourceActionContext(node=node)

    default_act = provider.get_default_action(context)
    assert default_act is not None
    assert default_act.id == "change_directory"
    assert default_act.is_default is True


def test_available_directory_actions_contain_stable_ids():
    """Verify available directory actions have stable IDs."""
    mock_service = MagicMock(spec=NodeService)
    provider = DirectoryActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="testdir",
        node_kind="resource",
        resource_type="directory",
        path="/some/path",
    )
    context = ResourceActionContext(node=node)

    actions = provider.get_available_actions(context)
    action_ids = [a.id for a in actions]
    assert "change_directory" in action_ids
    assert "copy_path" in action_ids
    assert "view_details" in action_ids


def test_copy_path_returns_resolved_path_without_clipboard():
    """Verify copy_path returns resolved path without using clipboard."""
    mock_service = MagicMock(spec=NodeService)
    # Mock node service to resolve the path
    mock_service.resolve_node_path.return_value = Path("/absolute/resolved/path")

    provider = DirectoryActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="testdir",
        node_kind="resource",
        resource_type="directory",
        path="/some/path",
    )
    context = ResourceActionContext(node=node)

    result = provider.execute("copy_path", context)
    assert result.success is True
    assert result.exit_app is False
    assert result.output_value == "/absolute/resolved/path"
    assert "Copied path" in result.message


def test_view_details_returns_structured_metadata():
    """Verify view_details action returns formatted metadata."""
    mock_service = MagicMock(spec=NodeService)
    mock_service.resolve_node_path.return_value = Path("/resolved/path")

    provider = DirectoryActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="testdir",
        node_kind="resource",
        resource_type="directory",
        path="/some/path",
        description="A test directory description",
    )
    context = ResourceActionContext(node=node)

    result = provider.execute("view_details", context)
    assert result.success is True
    assert result.exit_app is False
    assert "/resolved/path" in result.output_value
    assert "testdir" in result.output_value
    assert "A test directory description" in result.output_value


def test_invalid_node_kind_rejected_by_provider():
    """Verify DirectoryActionProvider rejects invalid kinds during execution."""
    mock_service = MagicMock(spec=NodeService)
    provider = DirectoryActionProvider(mock_service)

    workspace_node = Node(
        id=uuid.uuid4(),
        name="Workspace",
        node_kind="workspace",
    )
    context = ResourceActionContext(node=workspace_node)

    result = provider.execute("change_directory", context)
    assert result.success is False
    assert "Invalid node type" in result.error_message


def test_unknown_action_id_returns_failure():
    """Verify that calling an unknown action ID returns a failure result."""
    mock_service = MagicMock(spec=NodeService)
    mock_service.resolve_node_path.return_value = Path("/resolved")

    provider = DirectoryActionProvider(mock_service)
    node = Node(
        id=uuid.uuid4(),
        name="testdir",
        node_kind="resource",
        resource_type="directory",
        path="/some/path",
    )
    context = ResourceActionContext(node=node)

    result = provider.execute("invalid_action", context)
    assert result.success is False
    assert "Unknown action" in result.error_message
