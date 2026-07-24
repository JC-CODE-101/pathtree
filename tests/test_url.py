import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from pathtree.actions import (
    ResourceActionContext,
    ResourceActionRegistry,
    UrlActionProvider,
)
from pathtree.actions.base import ResourceActionResultTarget
from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import (
    NodeService,
    ValidationError,
)
from pathtree.utils.icons import NodeIconCatalog, icon_registry
from pathtree.utils.launcher import LaunchError, PlatformLauncher

# ==========================================
# 1. Validation & Service Layer Tests
# ==========================================


def test_create_valid_url_resource(session: Session):
    """Verify creating a valid URL resource."""
    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="My Workspace", node_kind="workspace")

    # Create http URL
    node_http = service.create_node(
        name="HTTP URL",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="http://example.com",
    )
    assert node_http.id is not None
    assert node_http.name == "HTTP URL"
    assert node_http.resource_type == "url"
    assert node_http.path == "http://example.com"

    # Create https URL
    node_https = service.create_node(
        name="HTTPS URL",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="https://github.com/coder/pathtree",
    )
    assert node_https.id is not None
    assert node_https.name == "HTTPS URL"
    assert node_https.resource_type == "url"
    assert node_https.path == "https://github.com/coder/pathtree"


def test_rejecting_invalid_or_malformed_url_on_creation(session: Session):
    """Verify rejecting invalid or malformed URLs on creation."""
    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="My Workspace", node_kind="workspace")

    # Empty URL path
    with pytest.raises(ValidationError) as exc:
        service.create_node(
            name="Empty URL",
            node_kind="resource",
            resource_type="url",
            parent_id=ws.id,
            path="",
        )
    assert "URL path cannot be empty" in str(exc.value)

    # Missing scheme (not starting with http:// or https://)
    with pytest.raises(ValidationError) as exc:
        service.create_node(
            name="No Scheme URL",
            node_kind="resource",
            resource_type="url",
            parent_id=ws.id,
            path="google.com",
        )
    assert "URL must start with http:// or https://" in str(exc.value)

    # Invalid scheme (ftp://)
    with pytest.raises(ValidationError) as exc:
        service.create_node(
            name="FTP URL",
            node_kind="resource",
            resource_type="url",
            parent_id=ws.id,
            path="ftp://ftp.example.com",
        )
    assert "URL must start with http:// or https://" in str(exc.value)

    # Malformed URL (no netloc/domain)
    with pytest.raises(ValidationError) as exc:
        service.create_node(
            name="Malformed URL",
            node_kind="resource",
            resource_type="url",
            parent_id=ws.id,
            path="https://",
        )
    assert "URL is invalid or malformed" in str(exc.value)


def test_editing_urls(session: Session):
    """Verify editing existing URLs behaves correctly."""
    repo = NodeRepository(session)
    service = NodeService(repo)

    ws = service.create_node(name="My Workspace", node_kind="workspace")
    url_node = service.create_node(
        name="Google",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="https://google.com",
    )

    # Update to valid URL
    updated = service.update_node(url_node.id, path="https://bing.com")
    assert updated.path == "https://bing.com"

    # Reject update to invalid URL
    with pytest.raises(ValidationError) as exc:
        service.update_node(url_node.id, path="invalid_url")
    assert "URL must start with http:// or https://" in str(exc.value)

    # Reject update to empty URL
    with pytest.raises(ValidationError) as exc:
        service.update_node(url_node.id, path="")
    assert "URL path cannot be empty" in str(exc.value)


def test_url_validation_reusable_scenarios():
    """Verify reusable validate_url covering various scheme/host scenarios."""
    mock_repo = MagicMock()
    service = NodeService(mock_repo)

    # valid HTTP URL
    assert service.validate_url("http://example.com/foo") == "http://example.com/foo"

    # valid HTTPS URL
    assert service.validate_url("https://example.com/foo") == "https://example.com/foo"

    # whitespace trimming
    assert (
        service.validate_url("   https://example.com/foo   ")
        == "https://example.com/foo"
    )

    # query strings and fragments preserved
    query_frag_url = "https://example.com/search?q=query#fragment"
    assert service.validate_url(query_frag_url) == query_frag_url

    # missing scheme
    with pytest.raises(ValidationError) as exc:
        service.validate_url("example.com")
    assert "URL must start with http:// or https://" in str(exc.value)

    # unsupported scheme
    with pytest.raises(ValidationError) as exc:
        service.validate_url("ftp://example.com")
    assert "URL must start with http:// or https://" in str(exc.value)

    # missing host
    with pytest.raises(ValidationError) as exc:
        service.validate_url("https://")
    assert "URL is invalid or malformed" in str(exc.value)


# ==========================================
# 2. Action Provider & Registry Tests
# ==========================================


def test_registry_resolves_url_action_provider():
    """Verify registry resolves UrlActionProvider."""
    registry = ResourceActionRegistry()
    mock_service = MagicMock(spec=NodeService)
    provider = UrlActionProvider(mock_service)
    registry.register("resource", "url", provider)

    resolved = registry.get_provider("resource", "url")
    assert resolved is provider
    assert resolved.resource_type == "url"


def test_url_default_action_is_open_url():
    """Verify URL default action is open_url."""
    mock_service = MagicMock(spec=NodeService)
    provider = UrlActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="Github Repo",
        node_kind="resource",
        resource_type="url",
        path="https://github.com",
    )
    context = ResourceActionContext(node=node)

    default_act = provider.get_default_action(context)
    assert default_act is not None
    assert default_act.id == "open_url"
    assert default_act.is_default is True


def test_available_url_action_ids_are_stable():
    """Verify available action IDs for URL are stable."""
    mock_service = MagicMock(spec=NodeService)
    provider = UrlActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="Github Repo",
        node_kind="resource",
        resource_type="url",
        path="https://github.com",
    )
    context = ResourceActionContext(node=node)

    actions = provider.get_available_actions(context)
    action_ids = [a.id for a in actions]
    assert len(action_ids) == 3
    assert "open_url" in action_ids
    assert "copy_url" in action_ids
    assert "view_details" in action_ids


# ==========================================
# 3. Browser Launch & Platform Tests
# ==========================================


@patch("sys.platform", "win32")
@patch("os.startfile", create=True)
def test_windows_browser_launch(mock_startfile):
    """Verify that on Windows, PlatformLauncher uses os.startfile to launch URL."""
    PlatformLauncher.open_url("https://example.com")
    mock_startfile.assert_called_once_with("https://example.com")


@patch("sys.platform", "linux")
@patch("subprocess.Popen")
@patch("shutil.which")
def test_linux_browser_launch(mock_which, mock_popen):
    """Verify that on Linux, PlatformLauncher uses xdg-open to launch URL."""
    mock_which.return_value = "/usr/bin/xdg-open"
    PlatformLauncher.open_url("https://example.com")
    mock_popen.assert_called_once_with(["xdg-open", "https://example.com"])


@patch("sys.platform", "darwin")
@patch("subprocess.Popen")
@patch("shutil.which")
def test_macos_browser_launch(mock_which, mock_popen):
    """Verify that on macOS, PlatformLauncher uses open to launch URL."""
    mock_which.return_value = "/usr/bin/open"
    PlatformLauncher.open_url("https://example.com")
    mock_popen.assert_called_once_with(["open", "https://example.com"])


@patch("sys.platform", "linux")
@patch("shutil.which")
def test_browser_launch_fails_safely_when_launcher_missing(mock_which):
    """Verify launch error is raised if platform browser launcher is missing."""
    mock_which.return_value = None
    with pytest.raises(LaunchError) as exc:
        PlatformLauncher.open_url("https://example.com")
    assert "not found" in str(exc.value)


@patch("subprocess.Popen")
def test_execute_open_url_success(mock_popen):
    """Verify execute open_url action completes successfully."""
    mock_service = MagicMock(spec=NodeService)
    mock_service.validate_url.side_effect = lambda u: u
    provider = UrlActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="Github",
        node_kind="resource",
        resource_type="url",
        path="https://github.com",
    )
    context = ResourceActionContext(node=node)

    with patch("shutil.which", return_value="/usr/bin/xdg-open"):
        with patch("sys.platform", "linux"):
            result = provider.execute("open_url", context)
            assert result.success is True
            assert result.exit_app is False
            assert "Successfully opened" in result.message


def test_invalid_stored_url_rejected_before_browser_launch():
    """Verify invalid stored URL rejected before browser launch in execute()."""
    mock_service = MagicMock(spec=NodeService)
    mock_service.validate_url.side_effect = ValidationError("Invalid scheme")
    provider = UrlActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="Bad URL",
        node_kind="resource",
        resource_type="url",
        path="ftp://bad-url.com",
    )
    context = ResourceActionContext(node=node)

    result = provider.execute("open_url", context)
    assert result.success is False
    assert "Invalid stored URL" in result.error_message


def test_invalid_stored_url_rejected_before_clipboard_copy():
    """Verify invalid stored URL rejected before clipboard copy in execute()."""
    mock_service = MagicMock(spec=NodeService)
    mock_service.validate_url.side_effect = ValidationError("Invalid host")
    provider = UrlActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="Bad URL",
        node_kind="resource",
        resource_type="url",
        path="https://",
    )
    context = ResourceActionContext(node=node)

    result = provider.execute("copy_url", context)
    assert result.success is False
    assert "Invalid stored URL" in result.error_message


# ==========================================
# 4. Clipboard Tests
# ==========================================


@patch("pathtree.utils.launcher.PlatformLauncher.copy_to_clipboard")
def test_execute_copy_url_success(mock_copy):
    """Verify copy_url executes successfully and copies URL."""
    mock_service = MagicMock(spec=NodeService)
    mock_service.validate_url.side_effect = lambda u: u
    provider = UrlActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="Github",
        node_kind="resource",
        resource_type="url",
        path="https://github.com",
    )
    context = ResourceActionContext(node=node)

    result = provider.execute("copy_url", context)
    assert result.success is True
    assert result.target == ResourceActionResultTarget.DETAILS
    assert result.output_value == "URL: https://github.com"
    mock_copy.assert_called_once_with("https://github.com")


# ==========================================
# 5. Icons Defaults & Registry
# ==========================================


def test_url_icon_defaults():
    """Verify standard and Nerd Fonts default icons for URLs."""
    node = Node(
        id=uuid.uuid4(),
        name="URL Node",
        node_kind="resource",
        resource_type="url",
        path="https://github.com",
    )

    # 1. Unicode Safe
    icon_registry.nerd_fonts_enabled = False
    catalog_safe = NodeIconCatalog(pack_name="unicode_safe")
    assert catalog_safe.get_default_icon("resource", "url") == "↗"
    assert icon_registry.get_icon(node) == "↗"

    # 2. Nerd Fonts
    icon_registry.nerd_fonts_enabled = True
    catalog_nerd = NodeIconCatalog(pack_name="nerd_fonts")
    assert catalog_nerd.get_default_icon("resource", "url") == "󰖟"
    assert icon_registry.get_icon(node) == "󰖟"


# ==========================================
# 6. Action Execution View Details
# ==========================================


def test_url_view_details():
    """Verify view_details generates correct URL metadata."""
    mock_service = MagicMock(spec=NodeService)
    provider = UrlActionProvider(mock_service)

    node = Node(
        id=uuid.uuid4(),
        name="Github Repo",
        node_kind="resource",
        resource_type="url",
        path="https://github.com/coder/pathtree",
        description="Core repo",
    )
    context = ResourceActionContext(node=node)

    result = provider.execute("view_details", context)
    assert result.success is True
    assert result.target == ResourceActionResultTarget.DETAILS
    assert "Name: Github Repo" in result.output_value
    assert "URL: https://github.com/coder/pathtree" in result.output_value
    assert "Scheme: https" in result.output_value
    assert "Domain: github.com" in result.output_value
    assert "Path: /coder/pathtree" in result.output_value
    assert "Description: Core repo" in result.output_value
