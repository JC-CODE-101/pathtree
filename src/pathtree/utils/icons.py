"""Central authoritative icon catalog, registry and option models for PathTree."""

import os
from dataclasses import dataclass

from pathtree.config.manager import config_manager


@dataclass
class IconOption:
    """A selectable icon representation with its symbol and semantic name."""

    symbol: str
    name: str


def classify_node_type(node_kind: str, resource_type: str | None) -> str:
    """Classify a node into one of the central catalog keys."""
    if node_kind == "workspace":
        return "workspace"
    elif node_kind == "folder":
        return "folder"
    elif node_kind == "system_group":
        return "system_group"
    elif node_kind == "resource":
        if resource_type in (
            "directory",
            "file",
            "script",
            "executable",
            "url",
            "launch_profile",
            "multi_launcher",
        ):
            return resource_type or "directory"
        return resource_type or "directory"
    return "directory"


# Central mappings for all semantic resource types in nerd, unicode, and ascii modes
ICONS_BY_MODE = {
    "nerd": {
        "workspace": "󰙅",
        "system": "󰒓",
        "custom": "󰙵",
        "directories": "󰉋",
        "files": "󰈔",
        "scripts": "󰧑",
        "executables": "󰆍",
        "urls": "󰖟",
        "launch_profiles": "󰓅",
        "multi_launchers": "󱓞",
        "detached_launch_profiles": "󰅚",
        "folder": "󰉋",
        "directory": "󰉋",
        "file": "󰈔",
        "script": "󰧑",
        "executable": "󰆍",
        "url": "󰖟",
        "launch_profile": "󰓅",
        "multi_launcher": "󱓞",
        "reference": "󰌷",
        "broken_reference": "󰅚",
        "pin": "󰐃",
        "filter": "󰺰",
        "generic_fallback": "󰈔",
    },
    "unicode": {
        "workspace": "◆",
        "system": "⚙",
        "custom": "🏡",
        "directories": "▪",
        "files": "▤",
        "scripts": "⚡",
        "executables": "⚙",
        "urls": "↗",
        "launch_profiles": "▶",
        "multi_launchers": "⚏",
        "detached_launch_profiles": "⚠",
        "folder": "⌂",  # '⌂' for safe compatibility with existing tests
        "directory": "▪",
        "file": "▤",
        "script": "⚡",
        "executable": "⚙",
        "url": "↗",
        "launch_profile": "▶",
        "multi_launcher": "⚏",
        "reference": "↗",
        "broken_reference": "⚠",
        "pin": "📌",
        "filter": "◉",
        "generic_fallback": "▪",
    },
    "ascii": {
        "workspace": "[WS]",
        "system": "[SYS]",
        "custom": "[CUST]",
        "directories": "[DIRS]",
        "files": "[FILES]",
        "scripts": "[SCRIPTS]",
        "executables": "[EXECS]",
        "urls": "[URLS]",
        "launch_profiles": "[PROFS]",
        "multi_launchers": "[MLCH]",
        "detached_launch_profiles": "[WARN]",
        "folder": "[F]",
        "directory": "[D]",
        "file": "[FILE]",
        "script": "[S]",
        "executable": "[X]",
        "url": "[U]",
        "launch_profile": "[P]",
        "multi_launcher": "[M]",
        "reference": "->",
        "broken_reference": "[BROKEN]",
        "pin": "[PIN]",
        "filter": "[FILTER]",
        "generic_fallback": "[FILE]",
    },
}

# The set of all default icons across all modes to correctly identify custom overrides
ALL_DEFAULT_ICONS = {icon for mode in ICONS_BY_MODE.values() for icon in mode.values()}


# Extension icons mapped for each mode for maximum consistency
EXTENSION_ICONS_BY_MODE = {
    "nerd": {
        ".py": "󰌠",
        ".sh": "󱆃",
        ".bash": "󱆃",
        ".zsh": "󱆃",
        ".md": "󰍔",
        ".pdf": "󰈦",
        ".txt": "󰈙",
        ".json": "󰘦",
        ".yaml": "󰘦",
        ".yml": "󰘦",
        ".toml": "󰘦",
        ".png": "󰋩",
        ".jpg": "󰋩",
        ".jpeg": "󰋩",
        ".svg": "󰋩",
        ".mp4": "󰿎",
        ".mp3": "󰎆",
        ".zip": "󰿺",
    },
    "unicode": {
        ".py": "▤",
        ".sh": "⚡",
        ".bash": "⚡",
        ".zsh": "⚡",
        ".md": "▤",
        ".pdf": "▤",
        ".txt": "▤",
        ".json": "▤",
        ".yaml": "▤",
        ".yml": "▤",
        ".toml": "▤",
        ".png": "▤",
        ".jpg": "▤",
        ".jpeg": "▤",
        ".svg": "▤",
        ".mp4": "▤",
        ".mp3": "▤",
        ".zip": "▤",
    },
    "ascii": {
        ".py": "[FILE]",
        ".sh": "[S]",
        ".bash": "[S]",
        ".zsh": "[S]",
        ".md": "[FILE]",
        ".pdf": "[FILE]",
        ".txt": "[FILE]",
        ".json": "[FILE]",
        ".yaml": "[FILE]",
        ".yml": "[FILE]",
        ".toml": "[FILE]",
        ".png": "[FILE]",
        ".jpg": "[FILE]",
        ".jpeg": "[FILE]",
        ".svg": "[FILE]",
        ".mp4": "[FILE]",
        ".mp3": "[FILE]",
        ".zip": "[FILE]",
    },
}


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
            IconOption("🏡", "Home"),
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
    "multi_launcher": {
        "default": IconOption("⚏", "Multi Launcher"),
        "options": [
            IconOption("⚏", "Multi Launcher"),
            IconOption("⧉", "Double Square"),
            IconOption("☰", "List"),
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
    "multi_launcher": {
        "default": IconOption("󱓞", "Multi Launcher"),
        "options": [
            IconOption("󱓞", "Multi Launcher"),
            IconOption("󰓅", "Rocket"),
            IconOption("󰒓", "Gear"),
        ],
    },
}


ASCII_PACK = {
    "workspace": {
        "default": IconOption("[WS]", "Workspace"),
        "options": [
            IconOption("[WS]", "Workspace"),
        ],
    },
    "folder": {
        "default": IconOption("[F]", "Folder"),
        "options": [
            IconOption("[F]", "Folder"),
        ],
    },
    "directory": {
        "default": IconOption("[D]", "Directory"),
        "options": [
            IconOption("[D]", "Directory"),
        ],
    },
    "file": {
        "default": IconOption("[FILE]", "File"),
        "options": [
            IconOption("[FILE]", "File"),
        ],
    },
    "script": {
        "default": IconOption("[S]", "Script"),
        "options": [
            IconOption("[S]", "Script"),
        ],
    },
    "executable": {
        "default": IconOption("[X]", "Executable"),
        "options": [
            IconOption("[X]", "Executable"),
        ],
    },
    "url": {
        "default": IconOption("[U]", "URL"),
        "options": [
            IconOption("[U]", "URL"),
        ],
    },
    "multi_launcher": {
        "default": IconOption("[M]", "Multi Launcher"),
        "options": [
            IconOption("[M]", "Multi Launcher"),
        ],
    },
}


class IconRegistry:
    """A centralized, extensible registry for resolving icons.

    Supports icon lookup by resource type, file extension, and custom overrides.
    Implements deterministic fallback resolution.
    """

    def __init__(self) -> None:
        """Initialize IconRegistry with default mappings and support settings."""
        pass

    @property
    def nerd_fonts_enabled(self) -> bool:
        """Compatibility property."""
        return self.get_icon_mode() == "nerd"

    @nerd_fonts_enabled.setter
    def nerd_fonts_enabled(self, val: bool) -> None:
        """Setter for testing/compatibility."""
        if val:
            config_manager.set_icon_mode("nerd")
        else:
            config_manager.set_icon_mode("unicode")

    def get_icon_mode(self) -> str:
        """Get the active icon mode from config."""
        # Under pytest, let environment variable PATHTREE_NERD_FONTS take precedence
        # to prevent test environment pollution by the user's config file.
        if "PYTEST_CURRENT_TEST" in os.environ:
            env_val = os.environ.get("PATHTREE_NERD_FONTS")
            if env_val is not None:
                if env_val.lower() in ("1", "true", "yes", "on"):
                    return "nerd"
                elif env_val.lower() in ("0", "false", "no", "off"):
                    return "unicode"

        mode = config_manager.get_icon_mode()
        if mode == "auto":
            return "unicode"
        return mode

    def resolve(
        self,
        node_kind: str,
        resource_type: str | None = None,
        system_role: str | None = None,
        is_reference: bool = False,
        is_broken: bool = False,
        custom_icon: str | None = None,
    ) -> str:
        """Centrally resolve the icon string based on the active icon mode."""
        mode = self.get_icon_mode()
        icons = ICONS_BY_MODE.get(mode, ICONS_BY_MODE["unicode"])

        # 1. Custom icon check
        if custom_icon is not None:
            stripped = custom_icon.strip()
            if stripped and stripped not in ALL_DEFAULT_ICONS:
                return stripped

        # 2. Reference status check
        if is_reference:
            if is_broken:
                return icons.get("broken_reference")
            return icons.get("reference")

        # 3. System role check
        if system_role is not None:
            if system_role in icons:
                return icons.get(system_role)

        # 4. Fallback classification lookup
        category = classify_node_type(node_kind, resource_type)
        if category in icons:
            return icons.get(category)

        # 5. Generic fallback
        return icons.get("generic_fallback", icons.get("file"))

    def register_resource_icon(
        self, resource_type: str, nerd_icon: str, safe_icon: str
    ) -> None:
        """Register or override an icon for a resource type."""
        ICONS_BY_MODE["nerd"][resource_type] = nerd_icon
        ICONS_BY_MODE["unicode"][resource_type] = safe_icon
        ICONS_BY_MODE["ascii"][resource_type] = safe_icon
        ALL_DEFAULT_ICONS.add(nerd_icon)
        ALL_DEFAULT_ICONS.add(safe_icon)

    def register_extension_icon(
        self, extension: str, nerd_icon: str, safe_icon: str
    ) -> None:
        """Register or override an icon for a file extension."""
        if not extension.startswith("."):
            extension = "." + extension
        ext = extension.lower()
        EXTENSION_ICONS_BY_MODE["nerd"][ext] = nerd_icon
        EXTENSION_ICONS_BY_MODE["unicode"][ext] = safe_icon
        EXTENSION_ICONS_BY_MODE["ascii"][ext] = safe_icon

    def get_icon(self, node) -> str:
        """Resolve the icon for a given node based on deterministic order."""
        if node is None:
            return self.resolve("resource", "file")

        # Custom icon check
        custom_icon = getattr(node, "icon", None)
        if custom_icon is not None:
            stripped = custom_icon.strip()
            if stripped and stripped not in ALL_DEFAULT_ICONS:
                return stripped

        # File extension check
        ext = self._get_node_extension(node)
        if ext:
            ext_lower = ext.lower()
            mode = self.get_icon_mode()
            extensions = EXTENSION_ICONS_BY_MODE.get(
                mode, EXTENSION_ICONS_BY_MODE["unicode"]
            )
            if ext_lower in extensions:
                return extensions[ext_lower]

        node_kind = getattr(node, "node_kind", "resource")
        resource_type = getattr(node, "resource_type", None)
        system_role = getattr(node, "system_role", None)

        is_reference = node_kind == "resource" and resource_type == "reference"
        is_broken = False
        orig_node = None

        if is_reference:
            try:
                from pathtree.database.connection import get_session
                from pathtree.database.repository import (
                    NodeRepository,
                    ResourceReferenceRepository,
                )
                from pathtree.services.node_service import NodeService
                from pathtree.services.resource_reference_service import (
                    ResourceReferenceService,
                )

                with get_session() as session:
                    ns = NodeService(NodeRepository(session))
                    rrs = ResourceReferenceService(
                        ns, ResourceReferenceRepository(session)
                    )
                    is_broken = rrs.is_broken(node.id)
                    if not is_broken:
                        orig_node = rrs.get_original_node(node.id)
            except Exception:
                pass

        if is_reference:
            if is_broken:
                return self.resolve(
                    node_kind,
                    resource_type,
                    system_role,
                    is_reference=True,
                    is_broken=True,
                )
            else:
                orig_kind = (
                    getattr(orig_node, "node_kind", "resource")
                    if orig_node
                    else "resource"
                )
                orig_type = (
                    getattr(orig_node, "resource_type", "file") if orig_node else "file"
                )
                orig_role = (
                    getattr(orig_node, "system_role", None) if orig_node else None
                )
                orig_custom_icon = (
                    getattr(orig_node, "icon", None) if orig_node else None
                )
                return self.resolve(
                    orig_kind, orig_type, orig_role, custom_icon=orig_custom_icon
                )

        return self.resolve(
            node_kind, resource_type, system_role, custom_icon=custom_icon
        )

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

    def get_pin_marker(self) -> str:
        """Get the pin marker symbol based on active icon mode."""
        mode = self.get_icon_mode()
        return ICONS_BY_MODE.get(mode, ICONS_BY_MODE["unicode"]).get("pin")

    def get_filter_marker(self) -> str:
        """Get the filter marker symbol based on active icon mode."""
        mode = self.get_icon_mode()
        return ICONS_BY_MODE.get(mode, ICONS_BY_MODE["unicode"]).get("filter")


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
            "ascii": ASCII_PACK,
        }
        if pack_name is None:
            mode = icon_registry.get_icon_mode()
            if mode == "nerd":
                pack_name = "nerd_fonts"
            elif mode == "ascii":
                pack_name = "ascii"
            else:
                pack_name = "unicode_safe"
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
        # Fallback to central registry resolve
        return icon_registry.resolve(node_kind, resource_type)

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
