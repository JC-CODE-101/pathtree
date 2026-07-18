"""Custom tree widget for displaying workspace nodes."""

import uuid
from typing import ClassVar

from textual.binding import Binding
from textual.widgets import Tree
from textual.widgets.tree import TreeNode as TextualTreeNode

from pathtree.models.node import Node
from pathtree.services.node_service import NodeService


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
        self.populate_tree()

    def populate_tree(self) -> None:
        """Populate branches from service-provided nodes recursively."""
        self.clear()
        roots = self.node_service.load_root_nodes()
        for root_node in roots:
            self.add_node_recursive(self.root, root_node)
        if not self.show_root and self.root.children:
            self.move_cursor(self.root.children[0])

    def add_node_recursive(
        self, parent_tree_node: TextualTreeNode[uuid.UUID], db_node: Node
    ) -> None:
        """Recursively load and add child nodes to the tree.

        Args:
            parent_tree_node: The parent Tree node to attach to.
            db_node: The Node from the database to attach.
        """
        children = self.node_service.load_children(db_node.id)
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
