"""Comprehensive unit tests for the centralized IconRegistry and Nerd Font support."""

from pathtree.utils.icons import IconRegistry


class MockNode:
    """Mock node for testing icon resolution without database overhead."""

    def __init__(
        self,
        node_kind: str = "resource",
        resource_type: str | None = None,
        path: str | None = None,
        name: str | None = None,
        icon: str | None = None,
    ) -> None:
        self.node_kind = node_kind
        self.resource_type = resource_type
        self.path = path
        self.name = name
        self.icon = icon


def test_icon_registry_resource_lookup() -> None:
    """Test lookup by resource type in both Nerd Font and standard modes."""
    registry = IconRegistry()

    # Enable Nerd Fonts
    registry.nerd_fonts_enabled = True
    workspace_node = MockNode(node_kind="workspace")
    assert registry.get_icon(workspace_node) == "󰙅"

    folder_node = MockNode(node_kind="folder")
    assert registry.get_icon(folder_node) == "󰉋"

    file_node = MockNode(node_kind="resource", resource_type="file")
    assert registry.get_icon(file_node) == "󰈔"

    script_node = MockNode(node_kind="resource", resource_type="script")
    assert registry.get_icon(script_node) == "󰧑"

    # Disable Nerd Fonts
    registry.nerd_fonts_enabled = False
    assert registry.get_icon(workspace_node) == "◆"
    assert registry.get_icon(folder_node) == "⌂"
    assert registry.get_icon(file_node) == "▤"
    assert registry.get_icon(script_node) == "⚡"


def test_icon_registry_extension_lookup() -> None:
    """Test lookup by file extension in both Nerd Font and standard modes."""
    registry = IconRegistry()

    # Enable Nerd Fonts
    registry.nerd_fonts_enabled = True
    python_node = MockNode(node_kind="resource", resource_type="file", path="main.py")
    assert registry.get_icon(python_node) == "󰌠"

    bash_node = MockNode(node_kind="resource", resource_type="script", path="run.sh")
    assert registry.get_icon(bash_node) == "󱆃"

    # Disable Nerd Fonts
    registry.nerd_fonts_enabled = False
    assert registry.get_icon(python_node) == "▤"
    assert registry.get_icon(bash_node) == "⚡"


def test_icon_registry_fallback_resolution() -> None:
    """Test deterministic fallback resolution.

    Order: file extension icon -> resource type icon -> generic default icon
    """
    registry = IconRegistry()
    registry.nerd_fonts_enabled = True

    # Case A: Extension match (should use extension icon)
    node_a = MockNode(node_kind="resource", resource_type="file", path="script.py")
    assert registry.get_icon(node_a) == "󰌠"

    # Case B: Unregistered extension, matches resource type (should use resource icon)
    node_b = MockNode(node_kind="resource", resource_type="script", path="script.xyz")
    assert registry.get_icon(node_b) == "󰧑"

    # Case C: Unknown resource type under resource (should use generic default)
    node_c = MockNode(node_kind="resource", resource_type="unknown_type")
    assert registry.get_icon(node_c) == "󰈔"


def test_icon_registry_custom_icons_preservation() -> None:
    """Test that explicit custom icons are preserved and not overridden."""
    registry = IconRegistry()
    registry.nerd_fonts_enabled = True

    # Custom icon '★' is not a registered default, so it should be preserved
    node_custom = MockNode(node_kind="workspace", icon="★")
    assert registry.get_icon(node_custom) == "★"

    # Default icon (e.g. '◆') with Nerd Fonts enabled resolves to '󰙅'
    node_default = MockNode(node_kind="workspace", icon="◆")
    assert registry.get_icon(node_default) == "󰙅"


def test_icon_registry_future_compatibility() -> None:
    """Test that the registry supports overrides, themes and dynamic registration."""
    registry = IconRegistry()
    registry.nerd_fonts_enabled = True

    # Register a new custom resource type icon
    registry.register_resource_icon("custom_resource", "󰛓", "★")
    node_new = MockNode(node_kind="resource", resource_type="custom_resource")
    assert registry.get_icon(node_new) == "󰛓"

    registry.nerd_fonts_enabled = False
    assert registry.get_icon(node_new) == "★"

    # Register a new custom extension icon
    registry.register_extension_icon(".custom_ext", "󰗀", "▲")
    node_ext = MockNode(
        node_kind="resource", resource_type="file", path="file.custom_ext"
    )
    registry.nerd_fonts_enabled = True
    assert registry.get_icon(node_ext) == "󰗀"

    registry.nerd_fonts_enabled = False
    assert registry.get_icon(node_ext) == "▲"
