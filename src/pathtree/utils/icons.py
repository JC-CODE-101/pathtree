"""Central icon catalog, registry and option models for PathTree."""

import os
from dataclasses import dataclass


@dataclass
class IconOption:
    """A selectable icon representation with its symbol and semantic name."""

    symbol: str
    name: str


def classify_node_type(node_kind: str, resource_type: str | None) -> str:
    """Classify a node into one of the central catalog keys.

    Supported keys:
    - workspace
    - folder
    - directory
    - file
    - script
    - executable
    - url
    """
    if node_kind == "workspace":
        return "workspace"
    elif node_kind == "folder":
        return "folder"
    elif node_kind == "resource":
        if resource_type in (
            "directory",
            "file",
            "script",
            "executable",
            "url",
        ):
            return resource_type or "directory"
        return resource_type or "directory"
    return "directory"


UNICODE_SAFE_PACK = {
    "workspace": {
        "default": IconOption("◆", "Diamond"),
        "options": [
            IconOption("◆", "Diamond"),
            IconOption("◇", "White Diamond"),
            IconOption("◈", "Nested Diamond"),
            IconOption("▲", "Triangle Up"),
        ],
    },
    "folder": {
        "default": IconOption("⌂", "House"),
        "options": [
            IconOption("⌂", "House"),
            IconOption("▣", "Nested Square"),
            IconOption("▰", "Rectangle"),
            IconOption("▱", "White Rectangle"),
        ],
    },
    "directory": {
        "default": IconOption("▪", "Small Square"),
        "options": [
            IconOption("▪", "Small Square"),
            IconOption("▫", "White Small Square"),
            IconOption("▬", "Bar"),
            IconOption("▭", "Rectangle"),
        ],
    },
    "file": {
        "default": IconOption("▤", "Document"),
        "options": [
            IconOption("▤", "Document"),
            IconOption("📄", "Page"),
            IconOption("🗎", "File Icon"),
            IconOption("☰", "Menu"),
        ],
    },
    "script": {
        "default": IconOption("⚡", "Lightning"),
        "options": [
            IconOption("⚡", "Lightning"),
            IconOption("⌁", "Electric"),
            IconOption("⚙", "Gear"),
            IconOption("⌬", "Hexagon"),
        ],
    },
    "executable": {
        "default": IconOption("⚙", "Gear"),
        "options": [
            IconOption("⚙", "Gear"),
            IconOption("⚒", "Hammer"),
            IconOption("❖", "Accent Diamond"),
            IconOption("✦", "Star"),
        ],
    },
    "url": {
        "default": IconOption("↗", "Arrow NE"),
        "options": [
            IconOption("↗", "Arrow NE"),
            IconOption("🌐", "Globe"),
            IconOption("🔗", "Link"),
            IconOption("➔", "Right Arrow"),
        ],
    },
}


NERD_FONTS_PACK = {
    "workspace": {
        "default": IconOption("󰙅", "Workspace"),
        "options": [
            IconOption("󰙅", "Workspace"),
            IconOption("󰠱", "White Workspace"),
            IconOption("󰓅", "Accent Workspace"),
            IconOption("󰒋", "Alt Workspace"),
        ],
    },
    "folder": {
        "default": IconOption("󰉋", "Folder"),
        "options": [
            IconOption("󰉋", "Folder"),
            IconOption("󰉖", "White Folder"),
            IconOption("󰉗", "Nested Folder"),
            IconOption("󰉘", "Open Folder"),
        ],
    },
    "directory": {
        "default": IconOption("󰉋", "Directory"),
        "options": [
            IconOption("󰉋", "Directory"),
            IconOption("󰉖", "White Directory"),
            IconOption("󰉗", "Nested Directory"),
            IconOption("󰉘", "Open Directory"),
        ],
    },
    "file": {
        "default": IconOption("󰈔", "File"),
        "options": [
            IconOption("󰈔", "File"),
            IconOption("󰈙", "Document"),
            IconOption("󰈚", "Text File"),
            IconOption("󰈛", "Alt File"),
        ],
    },
    "script": {
        "default": IconOption("󰧑", "Script"),
        "options": [
            IconOption("󰧑", "Script"),
            IconOption("󱗆", "Electric Script"),
            IconOption("󰧚", "Gear Script"),
            IconOption("󰒓", "Alt Script"),
        ],
    },
    "executable": {
        "default": IconOption("󰆍", "Executable"),
        "options": [
            IconOption("󰆍", "Executable"),
            IconOption("󰒓", "Gear Executable"),
            IconOption("󰋚", "Hammer Executable"),
            IconOption("󰓆", "Star Executable"),
        ],
    },
    "url": {
        "default": IconOption("󰖟", "URL"),
        "options": [
            IconOption("󰖟", "URL"),
            IconOption("󰌷", "Globe URL"),
            IconOption("󰒖", "Link URL"),
            IconOption("󰄖", "Arrow URL"),
        ],
    },
}


class IconRegistry:
    """A centralized, extensible registry for resolving icons.

    Supports icon lookup by resource type, file extension, and custom overrides.
    Implements deterministic fallback resolution:
        file extension icon -> resource type icon -> generic default icon
    """

    def __init__(self) -> None:
        """Initialize IconRegistry with default mappings and support settings."""
        self.nerd_fonts_enabled = os.environ.get(
            "PATHTREE_NERD_FONTS", "true"
        ).lower() in ("1", "true", "yes", "on")
        self._extension_icons: dict[str, dict[str, str]] = {}
        self._resource_icons: dict[str, dict[str, str]] = {}
        self._generic_default = {"nerd": "󰈔", "safe": "▪"}
        self._themes: dict[str, dict] = {}
        self._active_theme: str | None = None

        self._initialize_defaults()

    def _initialize_defaults(self) -> None:
        """Populate the registry with standard resource types and extension defaults."""
        # 1. Resource type defaults
        self.register_resource_icon("workspace", "󰙅", "◆")
        self.register_resource_icon("folder", "󰉋", "⌂")
        self.register_resource_icon("directory", "󰉋", "▪")
        self.register_resource_icon("file", "󰈔", "▤")
        self.register_resource_icon("script", "󰧑", "⚡")
        self.register_resource_icon("executable", "󰆍", "⚙")
        self.register_resource_icon("url", "󰖟", "↗")

        # 2. File extension defaults
        self.register_extension_icon(".py", "󰌠", "▤")
        self.register_extension_icon(".sh", "󱆃", "⚡")
        self.register_extension_icon(".bash", "󱆃", "⚡")
        self.register_extension_icon(".zsh", "󱆃", "⚡")
        self.register_extension_icon(".md", "󰍔", "▤")
        self.register_extension_icon(".pdf", "󰈦", "▤")
        self.register_extension_icon(".txt", "󰈙", "▤")
        self.register_extension_icon(".json", "󰘦", "▤")
        self.register_extension_icon(".yaml", "󰘦", "▤")
        self.register_extension_icon(".yml", "󰘦", "▤")
        self.register_extension_icon(".toml", "󰘦", "▤")
        self.register_extension_icon(".png", "󰋩", "▤")
        self.register_extension_icon(".jpg", "󰋩", "▤")
        self.register_extension_icon(".jpeg", "󰋩", "▤")
        self.register_extension_icon(".svg", "󰋩", "▤")
        self.register_extension_icon(".mp4", "󰿎", "▤")
        self.register_extension_icon(".mp3", "󰎆", "▤")
        self.register_extension_icon(".zip", "󰿺", "▤")

    def register_resource_icon(
        self, resource_type: str, nerd_icon: str, safe_icon: str
    ) -> None:
        """Register or override an icon for a resource type."""
        self._resource_icons[resource_type] = {"nerd": nerd_icon, "safe": safe_icon}

    def register_extension_icon(
        self, extension: str, nerd_icon: str, safe_icon: str
    ) -> None:
        """Register or override an icon for a file extension."""
        if not extension.startswith("."):
            extension = "." + extension
        self._extension_icons[extension.lower()] = {
            "nerd": nerd_icon,
            "safe": safe_icon,
        }

    def register_theme(self, theme_name: str, theme_data: dict) -> None:
        """Register a custom icon theme."""
        self._themes[theme_name] = theme_data

    def set_active_theme(self, theme_name: str | None) -> None:
        """Set the active theme, or clear it to use defaults."""
        if theme_name is None:
            self._active_theme = None
            return
        if theme_name in self._themes:
            self._active_theme = theme_name

    def get_icon(self, node) -> str:
        """Resolve the icon for a given node based on deterministic order.

        Resolution order:
            file extension icon
                ↓
            resource type icon
                ↓
            generic default icon
        """
        if node is None:
            return self._get_resolved_icon(self._generic_default)

        # 1. Custom icon check
        icon_attr = getattr(node, "icon", None)
        if icon_attr and not self._is_default_icon_symbol(icon_attr, node):
            return icon_attr

        # 2. File extension check
        ext = self._get_node_extension(node)
        if ext:
            ext_lower = ext.lower()
            if ext_lower in self._extension_icons:
                return self._get_resolved_icon(self._extension_icons[ext_lower])

        # 3. Resource type check
        node_kind = getattr(node, "node_kind", "resource")
        resource_type = getattr(node, "resource_type", None)
        category = classify_node_type(node_kind, resource_type)
        if category in self._resource_icons:
            return self._get_resolved_icon(self._resource_icons[category])

        # 4. Fallback to generic default
        return self._get_resolved_icon(self._generic_default)

    def _get_node_extension(self, node) -> str | None:
        """Helper to safely extract extension from node.path or node.name."""
        path = getattr(node, "path", None)
        if path:
            _, ext = os.path.splitext(path)
            if ext:
                return ext
        name = getattr(node, "name", None)
        if name:
            _, ext = os.path.splitext(name)
            if ext:
                return ext
        return None

    def _is_default_icon_symbol(self, icon: str, node) -> bool:
        """Check if the icon is the default icon for this specific node."""
        node_kind = getattr(node, "node_kind", "resource")
        resource_type = getattr(node, "resource_type", None)
        category = classify_node_type(node_kind, resource_type)

        # Check resource type defaults
        if category in self._resource_icons:
            item = self._resource_icons[category]
            if icon in (item["nerd"], item["safe"]):
                return True

        # Check extension defaults if applicable
        ext = self._get_node_extension(node)
        if ext:
            ext_lower = ext.lower()
            if ext_lower in self._extension_icons:
                item = self._extension_icons[ext_lower]
                if icon in (item["nerd"], item["safe"]):
                    return True

        # Check generic defaults
        if icon in (self._generic_default["nerd"], self._generic_default["safe"]):
            return True

        return False

    def _get_resolved_icon(self, icon_dict: dict[str, str]) -> str:
        """Resolve the icon using the dictionary based on nerd font availability."""
        if self.nerd_fonts_enabled:
            return icon_dict["nerd"]
        return icon_dict["safe"]


icon_registry = IconRegistry()


class NodeIconCatalog:
    """A central registry for default and recommended node icons.

    Supports custom icon packs and resolves default icons/safe fallbacks.
    Provides backwards compatibility for existing tests and dialogs.
    """

    def __init__(self, pack_name: str | None = None) -> None:
        """Initialize NodeIconCatalog with supported icon packs."""
        self.packs = {
            "unicode_safe": UNICODE_SAFE_PACK,
            "nerd_fonts": NERD_FONTS_PACK,
        }
        if pack_name is None:
            pack_name = (
                "nerd_fonts" if icon_registry.nerd_fonts_enabled else "unicode_safe"
            )
        self.current_pack_name = pack_name

    @property
    def current_pack(self) -> dict:
        """Retrieve the currently active icon pack."""
        return self.packs.get(self.current_pack_name, UNICODE_SAFE_PACK)

    def get_default_icon(self, node_kind: str, resource_type: str | None) -> str:
        """Resolve the default icon string from node_kind and resource_type."""
        category = classify_node_type(node_kind, resource_type)
        pack = self.current_pack
        if category in pack:
            return pack[category]["default"].symbol
        return "▪"

    def get_recommended_icons(
        self, node_kind: str, resource_type: str | None
    ) -> list[IconOption]:
        """List recommended icon options for specified node kind and type."""
        category = classify_node_type(node_kind, resource_type)
        pack = self.current_pack
        if category in pack:
            return pack[category]["options"]
        return [IconOption("▪", "Small Square")]

    def is_default_icon(
        self, icon: str | None, node_kind: str, resource_type: str | None
    ) -> bool:
        """Determine if a given icon matches the resolved default icon."""
        if not icon:
            return True
        return icon == self.get_default_icon(node_kind, resource_type)
