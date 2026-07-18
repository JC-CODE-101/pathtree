"""Custom tree widget for displaying workspace nodes."""

import uuid
from typing import ClassVar

from textual.binding import Binding
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
    ]

    def __init__(self, node_service: NodeService, **kwargs) -> None:
        """Initialize the NodeTreeView with a NodeService."""
        super().__init__("Root", **kwargs)
        self.node_service = node_service
        self.show_root = False
        self.load_error: str | None = None
        self.populate_tree()

    def populate_tree(self) -> None:
        """Populate branches from service-provided nodes recursively."""
        self.clear()
        self.load_error = None
        try:
            tree_nodes = self.node_service.get_validated_tree()
            for tree_node in tree_nodes:
                self.add_node_recursive(self.root, tree_node)
            if not self.show_root and self.root.children:
                self.move_cursor(self.root.children[0])
        except NodeServiceError as e:
            self.load_error = str(e)

    def add_node_recursive(
        self, parent_tree_node: TextualTreeNode[uuid.UUID], app_tree_node: TreeNode
    ) -> None:
        """Recursively add TreeNode hierarchy to the display tree.

        Args:
            parent_tree_node: The parent Tree node to attach to.
            app_tree_node: The TreeNode from the service layer to attach.
        """
        db_node = app_tree_node.node
        children = app_tree_node.children
        if children:
            tree_node = parent_tree_node.add(
                db_node.name, data=db_node.id, expand=False
            )
            for child in children:
                self.add_node_recursive(tree_node, child)
        else:
            parent_tree_node.add_leaf(db_node.name, data=db_node.id)

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
