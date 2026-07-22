"""Central icon catalog and option models for PathTree."""

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
        "default": IconOption("▸", "Arrow Right"),
        "options": [
            IconOption("▸", "Arrow Right"),
            IconOption("▶", "Play Arrow"),
            IconOption("▼", "Arrow Down"),
            IconOption("⌂", "House"),
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


class NodeIconCatalog:
    """A central registry for default and recommended node icons.

    Supports custom icon packs and resolves default icons/safe fallbacks.
    """

    def __init__(self, pack_name: str = "unicode_safe") -> None:
        """Initialize NodeIconCatalog with supported icon packs."""
        self.packs = {
            "unicode_safe": UNICODE_SAFE_PACK,
        }
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
