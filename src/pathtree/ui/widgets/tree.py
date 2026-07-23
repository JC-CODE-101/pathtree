"""Custom tree widget for displaying workspace nodes."""

import uuid
from typing import ClassVar

from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode as TextualTreeNode

from pathtree.services.node_service import NodeService, NodeServiceError, TreeNode


class IconText(Text):
    """Custom Rich Text subclass displaying icon before name."""

    def __init__(self, name: str, icon: str | None = None, *args, **kwargs) -> None:
        """Initialize IconText with name and optional icon."""
        self.name = name
        self.icon = icon
        if icon:
            super().__init__(f"{icon} {name}", *args, **kwargs)
        else:
            super().__init__(name, *args, **kwargs)

    def split(self, *args, **kwargs) -> list["IconText"]:
        """Overridden to prevent split from downgrading back to standard Text."""
        return [self]

    def __str__(self) -> str:
        """Return the clean node name without its prepended icon."""
        return self.name


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
    ]

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

    def __init__(self, node_service: NodeService, **kwargs) -> None:
        """Initialize the NodeTreeView with a NodeService."""
        super().__init__("Root", **kwargs)
        self.node_service = node_service
        self.show_root = False
        self.load_error: str | None = None
        self.populate_tree()

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

        def add_recursive(
            parent_tree_node: TextualTreeNode[uuid.UUID], app_tree_node: TreeNode
        ) -> None:
            db_node = app_tree_node.node
            children = app_tree_node.children
            should_expand = expand_all
            if expanded_node_ids is not None and db_node.id in expanded_node_ids:
                should_expand = True

            # Resolve icon
            from pathtree.utils.icons import NodeIconCatalog

            catalog = NodeIconCatalog()
            icon = db_node.icon
            if not icon:
                icon = catalog.get_default_icon(
                    db_node.node_kind, db_node.resource_type
                )

            label = IconText(db_node.name, icon)

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
