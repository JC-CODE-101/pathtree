"""Custom tree widget for displaying workspace nodes."""

import uuid
from typing import ClassVar

from rich.style import Style
from rich.text import Text
from textual import events
from textual._loop import loop_last
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.strip import Strip
from textual.widgets import Tree
from textual.widgets._tree import _TreeLine
from textual.widgets.tree import TreeNode as TextualTreeNode

from pathtree.services.node_service import NodeService, NodeServiceError, TreeNode


class IconText(Text):
    """Custom Rich Text subclass displaying semantically styled icon and name."""

    def __init__(self, name: str, icon: str | None = None, *args, **kwargs) -> None:
        self.name = name
        self.icon = icon
        super().__init__(*args, **kwargs)

    def split(self, *args, **kwargs) -> list["IconText"]:
        """Overridden to prevent split from downgrading back to standard Text."""
        return [self]

    def __str__(self) -> str:
        """Return the clean node name without its prepended icon."""
        return self.name


def build_node_label(node, context) -> IconText:
    """Build a rich, semantically styled tree node label."""
    # Extract context variables
    pinned = context.get("pinned", False)
    is_reference = context.get("is_reference", False)
    is_broken = context.get("is_broken", False)
    orig_node = context.get("orig_node", None)

    node_kind = getattr(node, "node_kind", "resource")
    resource_type = getattr(node, "resource_type", None)
    system_role = getattr(node, "system_role", None)
    custom_icon = getattr(node, "icon", None)

    from pathtree.utils.icons import icon_registry

    icon = ""
    if is_reference:
        if is_broken:
            icon = icon_registry.resolve(
                node_kind, resource_type, system_role, is_reference=True, is_broken=True
            )
        else:
            orig_kind = (
                getattr(orig_node, "node_kind", "resource") if orig_node else "resource"
            )
            orig_type = (
                getattr(orig_node, "resource_type", "file") if orig_node else "file"
            )
            orig_role = getattr(orig_node, "system_role", None) if orig_node else None
            orig_custom_icon = getattr(orig_node, "icon", None) if orig_node else None
            icon = icon_registry.resolve(
                orig_kind, orig_type, orig_role, custom_icon=orig_custom_icon
            )
    else:
        icon = icon_registry.resolve(
            node_kind, resource_type, system_role, custom_icon=custom_icon
        )

    pin_icon = icon
    if pinned:
        pin_icon = f"{icon_registry.get_pin_marker()} {icon}"

    label = IconText(node.name, icon=pin_icon)

    # Determine the icon and text colors/styles
    icon_style = ""
    name_style = ""

    # Resolve workspace accent if applicable
    workspace_accent = "default"
    if node_kind == "workspace":
        workspace_accent = getattr(node, "accent_color", "default") or "default"

    if node_kind == "workspace":
        accent_color_map = {
            "default": "bold #ffffff",
            "red": "bold #ff5555",
            "orange": "bold #ffaa00",
            "yellow": "bold #ffff55",
            "green": "bold #55ff55",
            "cyan": "bold #55ffff",
            "blue": "bold #5555ff",
            "purple": "bold #aa55ff",
            "magenta": "bold #ff55ff",
        }
        icon_style = accent_color_map.get(workspace_accent, "bold #ffffff")
        name_style = icon_style
    elif node_kind == "system_group":
        if system_role == "system":
            icon_style = "bold #6688cc"
            name_style = "bold #6688cc"
        elif system_role == "custom":
            icon_style = "bold #33cccc"
            name_style = "bold #33cccc"
        else:
            role_colors = {
                "directories": "bold #0088ff",
                "files": "bold #a0a0a0",
                "scripts": "bold #ffaa00",
                "executables": "bold #00ff00",
                "urls": "bold #00ffff",
                "launch_profiles": "bold #ffaa00",
                "multi_launchers": "bold #aa55ff",
            }
            icon_style = role_colors.get(system_role, "bold #a0a0a0")
            name_style = "dim"
    elif node_kind == "resource":
        if is_reference:
            if is_broken:
                icon_style = "bold #ff5555"
                name_style = "bold #ff5555 italic"
            else:
                orig_type = (
                    getattr(orig_node, "resource_type", "file") if orig_node else "file"
                )
                orig_colors = {
                    "directory": "bold #0088ff",
                    "file": "bold #a0a0a0",
                    "script": "bold #ffaa00",
                    "executable": "bold #00ff00",
                    "url": "bold #00ffff",
                    "launch_profile": "bold #ffaa00",
                    "multi_launcher": "bold #aa55ff",
                }
                icon_style = orig_colors.get(orig_type, "bold #a0a0a0")
                name_style = "italic"
        else:
            res_colors = {
                "directory": "bold #0088ff",
                "file": "bold #a0a0a0",
                "script": "bold #ffaa00",
                "executable": "bold #00ff00",
                "url": "bold #00ffff",
                "launch_profile": "bold #ffaa00",
                "multi_launcher": "bold #aa55ff",
            }
            icon_style = res_colors.get(resource_type, "bold #a0a0a0")
            name_style = ""
    else:
        icon_style = ""
        name_style = ""

    if pinned:
        pin_marker = icon_registry.get_pin_marker()
        label.append(pin_marker, style="bold #ffaa00")
        label.append(" ")

    label.append(icon, style=icon_style)
    label.append(" ")
    label.append(node.name, style=name_style)

    if is_reference:
        if is_broken:
            warning_ind = icon_registry.resolve(
                "resource", "reference", is_reference=True, is_broken=True
            )
            label.append(" ")
            label.append(warning_ind, style="bold #ff5555")
            label.append(" [Broken]", style="bold #ff5555")
        else:
            link_ind = icon_registry.resolve("resource", "reference", is_reference=True)
            label.append(" ")
            label.append(link_ind, style="bold #00ffff")

    return label


class NodeTreeView(Tree[uuid.UUID]):
    """Custom tree widget wrapping Textual's Tree."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "activate_cursor", "Activate", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("h", "collapse_or_parent", "Left/Collapse", show=False),
        Binding("left", "collapse_or_parent", "Left/Collapse", show=False),
        Binding("l", "expand_node", "Right/Expand", show=False),
        Binding("right", "expand_node", "Right/Expand", show=False),
        Binding("/", "focus_search", "Search", show=False),
        Binding("s", "focus_search", "Search", show=False),
        Binding("a", "add_node", "Add Node", show=False),
        Binding("e", "edit_node", "Edit Node", show=False),
        Binding("m", "move_node", "Move Node", show=False),
        Binding("d", "delete_node", "Delete Node", show=False),
        Binding("delete", "delete_node", "Delete Node", show=False),
        Binding("w", "next_workspace", "Next Workspace", show=False),
        Binding("W", "prev_workspace", "Prev Workspace", show=False),
        Binding("shift+w", "prev_workspace", "Prev Workspace", show=False),
        Binding("f", "next_folder", "Next Folder", show=False),
        Binding("F", "prev_folder", "Prev Folder", show=False),
        Binding("shift+f", "prev_folder", "Prev Folder", show=False),
        Binding("o", "open_action_menu", "Open Action Menu", show=True),
        Binding("O", "open_action_menu", "Open Action Menu", show=False),
        Binding("shift+o", "open_action_menu", "Open Action Menu", show=False),
        Binding("p", "open_pins_list", "Open Pins Screen", show=True),
        Binding("P", "open_pins_list", "Open Pins Screen", show=False),
        Binding("shift+p", "open_pins_list", "Open Pins Screen", show=False),
    ]

    class OpenPinsList(Message):
        """Sent when 'p' is pressed to open the Pins list screen."""

    class ActivateNode(Message):
        """Sent when a node is activated (via Enter or Double Click)."""

        def __init__(self, node_id: uuid.UUID) -> None:
            """Initialize with a node ID."""
            super().__init__()
            self.node_id = node_id

    class OpenActionMenu(Message):
        """Sent when the 'o' key is pressed to open the action menu."""

    class FocusSearch(Message):
        """Sent when the search focus key is pressed in the tree."""

    class AddNode(Message):
        """Sent when the 'a' key is pressed to add a node."""

    class EditNode(Message):
        """Sent when the 'e' key is pressed to edit a node."""

    class MoveNode(Message):
        """Sent when the 'm' key is pressed to move a node."""

    class DeleteNode(Message):
        """Sent when the 'd' or 'delete' key is pressed to delete a node."""

        """Sent when the search focus key is pressed in the tree."""

    def __init__(
        self, node_service: NodeService, spacing_mode: str = "normal", **kwargs
    ) -> None:
        """Initialize the NodeTreeView with a NodeService."""
        self._spacing_mode = spacing_mode
        super().__init__("Root", **kwargs)
        self.node_service = node_service
        self.show_root = False
        self.load_error: str | None = None

        from pathtree.database.repository import ResourceReferenceRepository
        from pathtree.services.resource_reference_service import (
            ResourceReferenceService,
        )

        self.reference_service = ResourceReferenceService(
            self.node_service,
            ResourceReferenceRepository(self.node_service.repository.session),
        )

        self.populate_tree()

    @property
    def spacing_mode(self) -> str:
        """Get the current visual spacing mode between Workspace root nodes."""
        return self._spacing_mode

    @spacing_mode.setter
    def spacing_mode(self, mode: str) -> None:
        """Set the visual spacing mode and rebuild the tree."""
        if mode not in ("compact", "normal", "wide"):
            raise ValueError("spacing_mode must be 'compact', 'normal', or 'wide'")
        self._spacing_mode = mode
        self.populate_tree()

    def _build(self) -> None:
        """Builds tree lines, inserting spacers between top-level Workspace nodes.

        MAINTENANCE NOTE:
        This implementation of visual workspace spacing relies directly on Textual's
        private tree internals (specifically: _tree_lines_cached, _TreeLine, and the
        _build / _render_line lifecycle).
        The supported Textual version must remain pinned in pyproject.toml. This
        implementation must be thoroughly revalidated before any Textual upgrade
        to prevent subtle rendering, selection, or navigation regressions.
        """
        lines = []
        add_line = lines.append
        root = self.root

        # Determine number of spacer lines
        num_spacers = 0
        if self._spacing_mode == "normal":
            num_spacers = 1
        elif self._spacing_mode == "wide":
            num_spacers = 2

        def add_node(path: list, node, last: bool) -> None:
            child_path = [*path, node]
            node._line = len(lines)
            add_line(_TreeLine(child_path, last))
            if node._expanded:
                for last_child, child in loop_last(node._children):
                    add_node(child_path, child, last_child)

        if self.show_root:
            add_node([], root, True)
        else:
            # Add top-level Workspace nodes with spacing
            for idx, node in enumerate(self.root._children):
                if idx > 0 and num_spacers > 0:
                    for _ in range(num_spacers):
                        spacer = _TreeLine([node], True)
                        spacer.is_spacer = True
                        add_line(spacer)
                add_node([], node, True)

        self._tree_lines_cached = lines

        guide_depth = self.guide_depth
        show_root = self.show_root
        get_label_width = self.get_label_width

        def get_line_width(line) -> int:
            if getattr(line, "is_spacer", False):
                return 0
            return get_label_width(line.node) + line._get_guide_width(
                guide_depth, show_root
            )

        if lines:
            width = max([get_line_width(line) for line in lines])
        else:
            width = self.size.width

        self.virtual_size = Size(width, len(lines))
        if self.cursor_line != -1:
            if self.cursor_node is not None:
                self.cursor_line = self.cursor_node._line
            if self.cursor_line >= len(lines):
                self.cursor_line = -1

    def _render_line(self, y: int, x1: int, x2: int, base_style: Style) -> Strip:
        """Render a tree line. If it is a spacer, render a blank strip."""
        tree_lines = self._tree_lines
        if y < len(tree_lines):
            line = tree_lines[y]
            if getattr(line, "is_spacer", False):
                return Strip.blank(self.size.width, base_style)
        return super()._render_line(y, x1, x2, base_style)

    def validate_cursor_line(self, value: int) -> int:
        """Prevent cursor line from landing on a spacer line, skipping over them."""
        tree_lines = self._tree_lines
        if not tree_lines:
            return -1
        max_idx = len(tree_lines) - 1
        value = max(0, min(value, max_idx))

        current = self.cursor_line
        if getattr(tree_lines[value], "is_spacer", False):
            if current == -1:
                for idx in range(value, len(tree_lines)):
                    if not getattr(tree_lines[idx], "is_spacer", False):
                        return idx
                return value

            # Skip in the direction of movement
            direction = 1 if value >= current else -1
            idx = value
            while 0 <= idx < len(tree_lines):
                if not getattr(tree_lines[idx], "is_spacer", False):
                    return idx
                idx += direction

            # Fallback to opposite search
            idx = value
            while 0 <= idx < len(tree_lines):
                if not getattr(tree_lines[idx], "is_spacer", False):
                    return idx
                idx -= direction

        return value

    def get_expanded_node_ids(self) -> set[uuid.UUID]:
        """Capture the IDs of expanded visible nodes recursively using UUIDs.

        Does not use labels.
        """
        expanded_ids = set()

        def traverse(node: TextualTreeNode[uuid.UUID]) -> None:
            if node.is_expanded and node.data is not None:
                expanded_ids.add(node.data)
            for child in node.children:
                traverse(child)

        traverse(self.root)
        return expanded_ids

    def load_tree(
        self,
        tree_nodes: list[TreeNode],
        selected_node_id: uuid.UUID | None = None,
        expand_all: bool = False,
        expanded_node_ids: set[uuid.UUID] | None = None,
    ) -> None:
        """Load the tree with a specific TreeNode hierarchy.

        Selects the specified node if possible. Clears any existing tree and builds
        from the provided nodes list.
        """
        self.clear()
        self.load_error = None

        node_map = {}

        # Pre-fetch currently pinned node IDs in a single query to avoid
        # database query regression
        try:
            from pathtree.database.repository import PinRepository

            pin_repo = PinRepository(self.node_service.repository.session)
            pinned_node_ids = {pin.node_id for pin in pin_repo.list_all()}
        except Exception:
            pinned_node_ids = set()

        # Bulk query for fast context resolution without N+1 queries
        # during recursive build
        try:
            all_refs = self.reference_service.repository.list_all()
            all_nodes = self.node_service.repository.list_all()
            nodes_by_id = {n.id: n for n in all_nodes}
            ref_by_node_id = {r.reference_node_id: r for r in all_refs}
        except Exception:
            nodes_by_id = {}
            ref_by_node_id = {}

        def add_recursive(
            parent_tree_node: TextualTreeNode[uuid.UUID], app_tree_node: TreeNode
        ) -> None:
            db_node = app_tree_node.node
            children = app_tree_node.children
            should_expand = expand_all
            if expanded_node_ids is not None and db_node.id in expanded_node_ids:
                should_expand = True

            # Resolve context in bulk
            is_ref = (
                db_node.node_kind == "resource" and db_node.resource_type == "reference"
            )
            is_broken = False
            orig_node = None
            if is_ref:
                ref_record = ref_by_node_id.get(db_node.id)
                if (
                    ref_record is None
                    or ref_record.original_node_id is None
                    or ref_record.original_node_id not in nodes_by_id
                ):
                    is_broken = True
                else:
                    is_broken = False
                    orig_node = nodes_by_id[ref_record.original_node_id]

            context_dict = {
                "pinned": db_node.id in pinned_node_ids,
                "is_reference": is_ref,
                "is_broken": is_broken,
                "orig_node": orig_node,
            }

            label = build_node_label(db_node, context_dict)

            if children:
                # Set expand to expand_all or if in expanded_node_ids
                tree_node = parent_tree_node.add(
                    label, data=db_node.id, expand=should_expand
                )
                node_map[db_node.id] = tree_node
                for child in children:
                    add_recursive(tree_node, child)
            else:
                tree_node = parent_tree_node.add_leaf(label, data=db_node.id)
                node_map[db_node.id] = tree_node

        for tree_node in tree_nodes:
            add_recursive(self.root, tree_node)

        # Select node_id if visible
        target_node = None
        if selected_node_id is not None:
            target_node = node_map.get(selected_node_id)

        if target_node is not None:
            # Ensure ancestors are expanded so target_node is visible
            curr = target_node.parent
            while curr is not None and curr != self.root:
                curr.expand()
                curr = curr.parent
            self.call_after_refresh(self.move_cursor, target_node)
            self.call_after_refresh(self.scroll_to_node, target_node)
        elif not self.show_root and self.root.children:
            self.call_after_refresh(self.move_cursor, self.root.children[0])

    def populate_tree(self) -> None:
        """Populate branches from service-provided nodes recursively."""
        try:
            tree_nodes = self.node_service.get_validated_tree()
            self.load_tree(tree_nodes)
        except NodeServiceError as e:
            self.clear()
            self.load_error = str(e)

    def action_focus_search(self) -> None:
        """Post FocusSearch message to focus the search input."""
        self.post_message(self.FocusSearch())

    def action_add_node(self) -> None:
        """Post AddNode message."""
        self.post_message(self.AddNode())

    def action_edit_node(self) -> None:
        """Post EditNode message."""
        self.post_message(self.EditNode())

    def action_move_node(self) -> None:
        """Post MoveNode message."""
        self.post_message(self.MoveNode())

    def action_delete_node(self) -> None:
        """Post DeleteNode message."""
        self.post_message(self.DeleteNode())

    def action_open_action_menu(self) -> None:
        """Post OpenActionMenu message."""
        self.post_message(self.OpenActionMenu())

    def action_open_pins_list(self) -> None:
        """Post OpenPinsList message."""
        self.post_message(self.OpenPinsList())

    def get_visible_nodes(self) -> list[TextualTreeNode[uuid.UUID]]:
        """Get all visible nodes in depth-first pre-order tree traversal."""
        visible = []

        def traverse(node: TextualTreeNode[uuid.UUID]) -> None:
            if node != self.root:
                visible.append(node)
            # Traverse children only if the node is root OR is expanded
            if node == self.root or node.is_expanded:
                for child in node.children:
                    traverse(child)

        traverse(self.root)
        return visible

    def _navigate_by_kind(self, target_kind: str, direction: int) -> None:
        """Shared helper to navigate between visible Workspace or Folder nodes."""
        visible_nodes = self.get_visible_nodes()
        if not visible_nodes:
            return

        current_node = self.cursor_node
        if current_node is None:
            return

        # 1. Single-pass DB query to load all node models
        all_nodes = self.node_service.repository.list_all()
        node_id_to_model = {n.id: n for n in all_nodes}

        # 2. Map visible nodes to their index
        visible_node_to_idx = {node: idx for idx, node in enumerate(visible_nodes)}

        # Helper to find containing workspace ID using the mapping
        def find_containing_workspace_id(
            tree_node: TextualTreeNode[uuid.UUID],
        ) -> uuid.UUID | None:
            curr = tree_node
            while curr is not None and curr != self.root:
                if curr.data is not None:
                    db_node = node_id_to_model.get(curr.data)
                    if db_node and db_node.node_kind == "workspace":
                        return db_node.id
                curr = curr.parent
            return None

        workspace_scope_id = None
        if target_kind == "folder":
            workspace_scope_id = find_containing_workspace_id(current_node)

        # 3. Filter candidates
        candidates = []
        for node in visible_nodes:
            if node.data is None:
                continue
            db_node = node_id_to_model.get(node.data)
            if not db_node:
                continue

            if db_node.node_kind != target_kind:
                continue

            if target_kind == "folder" and workspace_scope_id is not None:
                node_ws_id = find_containing_workspace_id(node)
                if node_ws_id != workspace_scope_id:
                    continue

            candidates.append(node)

        if not candidates:
            return

        if len(candidates) == 1:
            target = candidates[0]
            if current_node != target:
                self.move_cursor(target)
                self.scroll_to_node(target)
            return

        # Map each candidate to its index in the candidates list
        candidate_to_idx = {cand: idx for idx, cand in enumerate(candidates)}

        if current_node in candidate_to_idx:
            curr_idx = candidate_to_idx[current_node]
            next_idx = (curr_idx + direction) % len(candidates)
            target = candidates[next_idx]
        else:
            current_visible_idx = visible_node_to_idx.get(current_node, -1)

            if direction == 1:
                target = None
                for cand in candidates:
                    cand_vis_idx = visible_node_to_idx.get(cand, -1)
                    if cand_vis_idx > current_visible_idx:
                        target = cand
                        break
                if target is None:
                    target = candidates[0]
            else:
                target = None
                for cand in reversed(candidates):
                    cand_vis_idx = visible_node_to_idx.get(cand, -1)
                    if cand_vis_idx < current_visible_idx:
                        target = cand
                        break
                if target is None:
                    target = candidates[-1]

        if target is not None:
            self.move_cursor(target)
            self.scroll_to_node(target)

    def action_next_workspace(self) -> None:
        """Jump to the next visible Workspace node."""
        self._navigate_by_kind("workspace", 1)

    def action_prev_workspace(self) -> None:
        """Jump to the previous visible Workspace node."""
        self._navigate_by_kind("workspace", -1)

    def action_next_folder(self) -> None:
        """Jump to the next visible Folder node."""
        self._navigate_by_kind("folder", 1)

    def action_prev_folder(self) -> None:
        """Jump to the previous visible Folder node."""
        self._navigate_by_kind("folder", -1)

    def action_collapse_or_parent(self) -> None:
        """Collapse active directory node or go to parent if already collapsed."""
        node = self.cursor_node
        if node is None:
            return
        if node.is_expanded:
            node.collapse()
        else:
            parent = node.parent
            if parent is not None and parent != self.root:
                self.move_cursor(parent)

    def action_expand_node(self) -> None:
        """Expand active directory node."""
        node = self.cursor_node
        if node is None:
            return
        if not node.is_expanded and node.allow_expand:
            node.expand()

    def action_activate_cursor(self) -> None:
        """Activate the currently highlighted node."""
        node = self.cursor_node
        if node is not None and node.data is not None:
            self.post_message(self.ActivateNode(node.data))

    async def _on_click(self, event: events.Click) -> None:
        """Custom mouse click and double-click handling.

        Single left click selects the node and updates details but never
        executes actions.
        Double left click executes the default action on executable resource nodes.
        Workspace and Folder nodes are not treated as executable resources.
        """
        meta = event.style.meta
        if "line" in meta:
            cursor_line = meta["line"]
            tree_lines = self._tree_lines
            if cursor_line < len(tree_lines) and getattr(
                tree_lines[cursor_line], "is_spacer", False
            ):
                event.prevent_default()
                event.stop()
                return

            if meta.get("toggle", False):
                await super()._on_click(event)
                return

            if event.chain >= 2:
                node = self.get_node_at_line(cursor_line)
                if node is not None and node.data is not None:
                    db_node = self.node_service.get_node(node.data)
                    if db_node is not None and db_node.node_kind == "resource":
                        self.post_message(self.ActivateNode(node.data))
                event.stop()
                return

        await super()._on_click(event)
