"""Custom tree widget for displaying workspace nodes."""

import uuid
from typing import ClassVar

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode as TextualTreeNode

from pathtree.services.node_service import NodeService, NodeServiceError, TreeNode


class NodeTreeView(Tree[uuid.UUID]):
    """Custom tree widget wrapping Textual's Tree."""

    BINDINGS: ClassVar[list[Binding]] = [
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
    ]

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

    def load_tree(
        self,
        tree_nodes: list[TreeNode],
        selected_node_id: uuid.UUID | None = None,
        expand_all: bool = False,
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
            if children:
                # Set expand to expand_all when query is active
                tree_node = parent_tree_node.add(
                    db_node.name, data=db_node.id, expand=expand_all
                )
                node_map[db_node.id] = tree_node
                for child in children:
                    add_recursive(tree_node, child)
            else:
                tree_node = parent_tree_node.add_leaf(db_node.name, data=db_node.id)
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
