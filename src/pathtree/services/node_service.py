import uuid
from collections.abc import Sequence
from pathlib import Path

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node


class NodeServiceError(Exception):
    """Base exception class for all NodeService errors."""


class SelfParentError(NodeServiceError):
    """Raised when a node is set as its own parent."""


class ValidationError(NodeServiceError):
    """Raised when node model validation fails."""


class CycleError(NodeServiceError):
    """Raised when a cycle/descendant loop is detected."""


class ParentNotFoundError(NodeServiceError):
    """Raised when a parent node reference does not exist in the database."""


class NodeNotFoundError(NodeServiceError):
    """Raised when a requested node does not exist in the database."""


class NoPathError(NodeServiceError):
    """Raised when a node does not have a configured path."""


class PathNotFoundError(NodeServiceError):
    """Raised when a node's configured path does not exist on the filesystem."""


class PathNotADirectoryError(NodeServiceError):
    """Raised when a node's configured path exists but is not a directory."""


class TreeNode:
    """A deterministic nested tree node representation."""

    def __init__(self, node: Node, children: list["TreeNode"] | None = None) -> None:
        """Initialize a TreeNode with its corresponding Node and children."""
        self.node = node
        self.children = children if children is not None else []

    def __repr__(self) -> str:
        return f"<TreeNode node={self.node.name} children_count={len(self.children)}>"


class NodeService:
    """Service layer coordinating Node business operations and tree assembly.

    Uses NodeRepository for all data access.
    Does not access SQLModel sessions or execute SQL directly.
    """

    def __init__(self, repository: NodeRepository) -> None:
        """Initialize the NodeService with a NodeRepository."""
        self.repository = repository

    def load_root_nodes(self) -> Sequence[Node]:
        """Load root-level nodes (nodes with parent_id = None).

        Preserves repository ordering (sort_order, then created_at).
        """
        return self.repository.list_children(None)

    def load_children(self, node_id: uuid.UUID) -> Sequence[Node]:
        """Load child nodes for a given node.

        Preserves repository ordering (sort_order, then created_at).
        """
        return self.repository.list_children(node_id)

    def build_tree(self, flat_nodes: Sequence[Node]) -> list[TreeNode]:
        """Assemble a deterministic nested tree of TreeNodes from flat Node records.

        Preserves repository ordering. Handles empty lists correctly.
        Checks for cycles in the stored records and raises CycleError to protect
        against infinite recursion or malformed cyclic DB data.
        """
        if not flat_nodes:
            return []

        # 1. Build an adjacency map and a list of node IDs for cycle detection
        node_ids = {n.id for n in flat_nodes}
        nodes_by_parent: dict[uuid.UUID | None, list[Node]] = {}
        for n in flat_nodes:
            nodes_by_parent.setdefault(n.parent_id, []).append(n)

        # 2. Complete Cycle Detection across the whole list (using three-color DFS)
        # To handle any disconnected components containing cycles as well.
        state: dict[uuid.UUID, str] = {}  # id -> "visiting" or "visited"

        def detect_cycle_dfs(u_id: uuid.UUID) -> bool:
            state[u_id] = "visiting"
            for child_node in nodes_by_parent.get(u_id, []):
                v_id = child_node.id
                v_state = state.get(v_id)
                if v_state == "visiting":
                    return True
                elif v_state is None:
                    if detect_cycle_dfs(v_id):
                        return True
            state[u_id] = "visited"
            return False

        for n in flat_nodes:
            if n.id not in state:
                if detect_cycle_dfs(n.id):
                    raise CycleError(
                        f"Cycle detected in node hierarchy at/under {n.name}."
                    )

        # 3. Build tree recursively starting from root-level nodes
        # If a node's parent is not in flat_nodes, we treat it as a root-level node
        # to handle malformed data gracefully or partial subtrees.
        # But normally, roots have parent_id = None.
        roots = []
        for n in flat_nodes:
            if n.parent_id is None or n.parent_id not in node_ids:
                roots.append(n)

        # Ensure roots are unique (based on ID) and preserve list ordering
        seen_roots = set()
        ordered_roots = []
        for r in roots:
            if r.id not in seen_roots:
                seen_roots.add(r.id)
                ordered_roots.append(r)

        def build_subtree(node: Node) -> TreeNode:
            # Children are already sorted because they were added to nodes_by_parent
            # in the order of flat_nodes, which preserves repository ordering.
            children_list = nodes_by_parent.get(node.id, [])
            sub_trees = [build_subtree(child) for child in children_list]
            return TreeNode(node, sub_trees)

        return [build_subtree(root) for root in ordered_roots]

    def validate_parent(self, node_id: uuid.UUID, parent_id: uuid.UUID | None) -> None:
        """Validate parent-child relationship to prevent invalid hierarchies.

        - Prevents a node from becoming its own parent.
        - Prevents moving a node below one of its descendants.
        - Rejects references to nonexistent parent nodes.

        Raises clear, project-specific exceptions for invalid operations.
        """
        # 1. Prevent a node from becoming its own parent
        if parent_id is not None and node_id == parent_id:
            raise SelfParentError(f"Node {node_id} cannot be its own parent.")

        # 2. Reject references to nonexistent parent nodes
        if parent_id is not None:
            parent_node = self.repository.get_by_id(parent_id)
            if parent_node is None:
                raise ParentNotFoundError(f"Parent node {parent_id} does not exist.")

        # 3. Prevent moving a node below one of its descendants
        if parent_id is not None:
            curr_id: uuid.UUID | None = parent_id
            visited = set()
            while curr_id is not None:
                if curr_id == node_id:
                    raise CycleError(
                        f"Node {node_id} cannot be moved "
                        f"below its descendant node {parent_id}."
                    )
                if curr_id in visited:
                    # Detected an existing loop in database parent pointers
                    raise CycleError("Cycle detected in parent hierarchy.")
                visited.add(curr_id)

                p_node = self.repository.get_by_id(curr_id)
                if p_node is None:
                    # Nonexistent reference should have been caught,
                    # but we handle it gracefully here.
                    raise ParentNotFoundError(f"Parent node {curr_id} does not exist.")
                curr_id = p_node.parent_id

    def resolve_node_path(self, node_id: uuid.UUID) -> Path:
        """Resolve the selected node's local directory path.

        Returns a valid normalized Path only when the node contains an
        existing directory. Clearly distinguishes:
          - node does not exist (raises NodeNotFoundError)
          - node has no path (raises NoPathError)
          - path does not exist (raises PathNotFoundError)
          - path exists but is not a directory (raises PathNotADirectoryError)

        Does not change the current working directory.
        """
        node = self.repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} does not exist.")

        if not node.path:
            raise NoPathError(f"Node '{node.name}' ({node_id}) has no configured path.")

        path = Path(node.path).resolve()
        if not path.exists():
            raise PathNotFoundError(
                f"Path '{node.path}' for node '{node.name}' does not exist."
            )
        if not path.is_dir():
            raise PathNotADirectoryError(
                f"Path '{node.path}' for node '{node.name}' "
                "exists but is not a directory."
            )

        return path

    def get_node(self, node_id: uuid.UUID) -> Node | None:
        """Retrieve a node by its ID through the service.

        Args:
            node_id: The UUID of the node to retrieve.

        Returns:
            The Node object if found, otherwise None.
        """
        return self.repository.get_by_id(node_id)

    def get_validated_tree(self) -> list[TreeNode]:
        """Fetch all nodes and build a cycle-protected nested tree structure.

        Raises:
            CycleError: If a loop/cycle is detected in the hierarchy.
        """
        flat_nodes = self.repository.list_all()
        return self.build_tree(flat_nodes)

    def validate_node(self, node: Node) -> None:
        """Validate node kind and resource type combination.

        Only specific combinations of node_kind and resource_type are valid:
        - node_kind = "workspace" and resource_type = None
        - node_kind = "folder" and resource_type = None
        - node_kind = "resource" and resource_type = "directory"

        Raises:
            ValidationError: If any other combination is provided.
        """
        kind = node.node_kind
        res_type = node.resource_type

        valid = False
        if kind == "workspace" and res_type is None:
            valid = True
        elif kind == "folder" and res_type is None:
            valid = True
        elif kind == "resource" and res_type == "directory":
            valid = True

        if not valid:
            raise ValidationError(
                f"Invalid combination: node_kind='{kind}', resource_type='{res_type}'."
            )
