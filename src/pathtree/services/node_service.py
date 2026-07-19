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


class InvalidParentKindError(NodeServiceError):
    """Raised when parent node is a resource node or other invalid kind."""


class DuplicateSiblingNameError(NodeServiceError):
    """Raised when a sibling node already has the same normalized name."""


class EmptyNodeNameError(NodeServiceError):
    """Raised when a node name is empty after trimming."""


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

    def validate_parent(
        self,
        node_id: uuid.UUID | None,
        parent_id: uuid.UUID | None,
    ) -> None:
        """Validate parent-child relationship to prevent invalid hierarchies.

        - Prevents a node from becoming its own parent.
        - Prevents moving a node below one of its descendants.
        - Rejects references to nonexistent parent nodes.
        - Rejects parent nodes that are resources (InvalidParentKindError).

        Raises clear, project-specific exceptions for invalid operations.
        """
        if parent_id is None:
            return

        # 1. Prevent a node from becoming its own parent
        if node_id is not None and node_id == parent_id:
            raise SelfParentError(f"Node {node_id} cannot be its own parent.")

        # 2. Reject references to nonexistent parent nodes
        parent_node = self.repository.get_by_id(parent_id)
        if parent_node is None:
            raise ParentNotFoundError(f"Parent node {parent_id} does not exist.")

        # 3. Rejects parent nodes that are not in {"workspace", "folder"}
        if parent_node.node_kind not in {"workspace", "folder"}:
            raise InvalidParentKindError(
                f"Parent node {parent_id} kind "
                f"'{parent_node.node_kind}' is not allowed."
            )

        if node_id is not None:
            # 4. Prevent moving a node below one of its descendants
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

    def create_node(
        self,
        name: str,
        node_kind: str,
        resource_type: str | None = None,
        parent_id: uuid.UUID | None = None,
        path: str | None = None,
        description: str | None = None,
        icon: str | None = None,
        is_favorite: bool = False,
        is_temporary: bool = False,
        sort_order: int = 0,
    ) -> Node:
        """Create a new node after performing validations.

        Validations:
        - name trimming & empty check
        - parent validation
        - sibling name uniqueness check under the same parent
        - combination check of node_kind and resource_type
        - structural node contains no path check
        """
        # 1. Trim name and reject empty names
        if name is None:
            raise EmptyNodeNameError("Name cannot be None.")
        trimmed_name = name.strip()
        if not trimmed_name:
            raise EmptyNodeNameError("Name cannot be empty after trimming.")

        # 2. Validate requested parent (if parent_id is not None)
        self.validate_parent(None, parent_id)

        # 3. Validate sibling-name uniqueness
        if self.repository.has_sibling_with_name(parent_id, trimmed_name):
            raise DuplicateSiblingNameError(
                f"A sibling node with the name '{trimmed_name}' already exists."
            )

        # 4. Normalize directory paths where safely possible without requiring existence
        import os

        normalized_path = None
        if path is not None:
            trimmed_path = path.strip()
            if trimmed_path:
                normalized_path = os.path.normpath(trimmed_path)

        # 5. Check structural workspace and folder nodes must not contain a path
        if node_kind in ("workspace", "folder") and normalized_path is not None:
            raise ValidationError("Structural nodes must not contain a path.")

        # 6. Assign resource_type="directory" explicitly for directory resources
        if node_kind == "resource" and resource_type is None:
            resource_type = "directory"

        node = Node(
            name=trimmed_name,
            node_kind=node_kind,
            resource_type=resource_type,
            parent_id=parent_id,
            path=normalized_path,
            description=description,
            icon=icon,
            is_favorite=is_favorite,
            is_temporary=is_temporary,
            sort_order=sort_order,
        )

        self.validate_node(node)
        return self.repository.create(node)

    def update_node(self, node_id: uuid.UUID, **kwargs) -> Node:
        """Update an existing node after performing validations.

        Modifies name, description, icon, path, sort_order, is_favorite, is_temporary.
        Supports temporary promotion to permanent.
        Rejects conversion of permanent to temporary.
        Rejects arbitrary node_kind / resource_type conversions.
        Structural nodes must not retain a path.
        """
        node = self.repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} does not exist.")

        if "parent_id" in kwargs:
            raise ValidationError(
                "To change parent, use move_node instead of update_node."
            )

        allowed_fields = {
            "name",
            "description",
            "icon",
            "path",
            "sort_order",
            "is_favorite",
            "is_temporary",
        }
        for kw in kwargs:
            if kw not in allowed_fields:
                raise ValidationError(f"Unsupported field for update: {kw}")

        # Local variables to hold proposed state
        proposed_name = node.name
        proposed_description = node.description
        proposed_icon = node.icon
        proposed_path = node.path
        proposed_sort_order = node.sort_order
        proposed_is_favorite = node.is_favorite
        proposed_is_temporary = node.is_temporary

        # Check temporary to permanent demotion rules
        if "is_temporary" in kwargs:
            val = kwargs["is_temporary"]
            if val is True and not node.is_temporary:
                raise ValidationError("Permanent nodes cannot be demoted to temporary.")
            proposed_is_temporary = val

        # Handle name change
        if "name" in kwargs:
            new_name = kwargs["name"]
            if new_name is None:
                raise EmptyNodeNameError("Name cannot be None.")
            trimmed_name = new_name.strip()
            if not trimmed_name:
                raise EmptyNodeNameError("Name cannot be empty after trimming.")
            if self.repository.has_sibling_with_name(
                node.parent_id, trimmed_name, exclude_id=node.id
            ):
                raise DuplicateSiblingNameError(
                    f"A sibling node with the name '{trimmed_name}' already exists."
                )
            proposed_name = trimmed_name

        # Handle path change
        if "path" in kwargs:
            import os

            new_path = kwargs["path"]
            normalized_path = None
            if new_path is not None:
                trimmed_path = new_path.strip()
                if trimmed_path:
                    normalized_path = os.path.normpath(trimmed_path)

            if (
                node.node_kind in ("workspace", "folder")
                and normalized_path is not None
            ):
                raise ValidationError("Structural nodes must not contain a path.")
            proposed_path = normalized_path

        # Handle description, icon, sort_order, is_favorite
        if "description" in kwargs:
            proposed_description = kwargs["description"]
        if "icon" in kwargs:
            proposed_icon = kwargs["icon"]
        if "sort_order" in kwargs:
            proposed_sort_order = kwargs["sort_order"]
        if "is_favorite" in kwargs:
            proposed_is_favorite = kwargs["is_favorite"]

        # Final checks on a temporary / dummy Node
        dummy_node = Node(
            id=node.id,
            parent_id=node.parent_id,
            name=proposed_name,
            node_kind=node.node_kind,
            resource_type=node.resource_type,
            path=proposed_path,
            description=proposed_description,
            icon=proposed_icon,
            sort_order=proposed_sort_order,
            is_favorite=proposed_is_favorite,
            is_temporary=proposed_is_temporary,
        )
        self.validate_node(dummy_node)
        if (
            dummy_node.node_kind in ("workspace", "folder")
            and dummy_node.path is not None
        ):
            raise ValidationError("Structural nodes must not contain a path.")

        # Mutate the actual managed node only after all validations have succeeded
        node.name = proposed_name
        node.description = proposed_description
        node.icon = proposed_icon
        node.path = proposed_path
        node.sort_order = proposed_sort_order
        node.is_favorite = proposed_is_favorite
        node.is_temporary = proposed_is_temporary

        return self.repository.update(node)

    def move_node(self, node_id: uuid.UUID, new_parent_id: uuid.UUID | None) -> Node:
        """Move a node to a new parent atomically.

        Allows root, workspace, or folder as destinations.
        Rejects resource parents, self-parenting, and descendant cycle.
        Enforces sibling uniqueness in the destination.
        Returns unchanged node immediately if moving to current parent (safe no-op).
        """
        node = self.repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} does not exist.")

        # Safe no-op if moving to current parent
        if node.parent_id == new_parent_id:
            return node

        # Validate parent kind and cycle / self-parenting
        self.validate_parent(node_id, new_parent_id)

        # Validate sibling name clash in destination
        if self.repository.has_sibling_with_name(
            new_parent_id, node.name, exclude_id=node.id
        ):
            raise DuplicateSiblingNameError(
                f"A sibling with name '{node.name}' already exists in the destination."
            )

        node.parent_id = new_parent_id
        return self.repository.update(node)

    def count_descendants(self, node_id: uuid.UUID) -> int:
        """Count all descendants of a given node.

        Raises NodeNotFoundError if the node does not exist.
        """
        node = self.repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} does not exist.")
        from pathtree.database.repository import RepositoryCycleError

        try:
            return len(self.repository.get_descendants(node_id))
        except RepositoryCycleError as e:
            raise CycleError(str(e)) from e

    def delete_node(self, node_id: uuid.UUID, recursive: bool = True) -> bool:
        """Delete a node and its descendants if recursive=True.

        If recursive=False and descendants exist, raises a ValidationError.
        Raises NodeNotFoundError if the node does not exist.
        """
        node = self.repository.get_by_id(node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {node_id} does not exist.")

        from pathtree.database.repository import RepositoryCycleError

        try:
            if not recursive:
                descendants = self.repository.get_descendants(node_id)
                if descendants:
                    raise ValidationError(
                        f"Node {node_id} has descendants and "
                        "cannot be deleted non-recursively."
                    )

            self.repository.delete_recursive(node_id)
        except RepositoryCycleError as e:
            raise CycleError(str(e)) from e
        return True

    def get_parent_choices(
        self, exclude_node_id: uuid.UUID | None = None
    ) -> list[tuple[str, uuid.UUID | None]]:
        """Generate a list of parent choices in tree order.

        Format: (label, node_id)
        Where label is e.g. "Root", "Workspace Name", "Workspace Name / Folder Name"
        """
        choices: list[tuple[str, uuid.UUID | None]] = [("Root", None)]

        try:
            tree_nodes = self.get_validated_tree()
        except CycleError:
            # If tree contains cycles, default to just Root to prevent crashing
            return choices

        def traverse(tree_node: TreeNode, parent_label: str) -> None:
            node = tree_node.node
            if exclude_node_id is not None and node.id == exclude_node_id:
                return  # Skip self and all descendants

            # Construct label
            if parent_label == "Root":
                current_label = node.name
            else:
                current_label = f"{parent_label} / {node.name}"

            # If workspace or folder, it's a valid choice
            if node.node_kind in ("workspace", "folder"):
                choices.append((current_label, node.id))

            for child in tree_node.children:
                traverse(child, current_label)

        for root_tree_node in tree_nodes:
            traverse(root_tree_node, "Root")

        return choices

    def search_nodes(
        self,
        query: str | None = None,
        type_filter: str | None = None,
    ) -> list[TreeNode]:
        """Perform search and return a filtered tree of TreeNodes.

        Parses query if it has a 'type:...' filter pattern or handles them directly.
        Returns the entire tree if both query and type_filter are empty or None.
        Preserves complete ancestor chains for matching nodes.
        """
        clean_query = query
        actual_type_filter = type_filter

        if query:
            parts = query.split()
            filtered_parts = []
            for part in parts:
                if part.startswith("type:"):
                    tf_val = part[5:].lower()
                    if tf_val in ("workspace", "folder", "directory"):
                        actual_type_filter = tf_val
                else:
                    filtered_parts.append(part)
            clean_query = " ".join(filtered_parts) if filtered_parts else None

        # Build full tree
        full_tree = self.get_validated_tree()

        # If no clean_query and no actual_type_filter, return the full tree
        if not clean_query and not actual_type_filter:
            return full_tree

        # Helper to recursively filter a TreeNode
        def filter_node(tree_node: TreeNode) -> TreeNode | None:
            # 1. Filter children recursively
            filtered_children = []
            for child in tree_node.children:
                res = filter_node(child)
                if res is not None:
                    filtered_children.append(res)

            # 2. Check if this node matches itself
            matches_self = True

            # Match query
            if clean_query:
                q = clean_query.casefold()
                name_match = q in tree_node.node.name.casefold()
                path_match = (
                    tree_node.node.path is not None
                    and q in tree_node.node.path.casefold()
                )
                desc_match = (
                    tree_node.node.description is not None
                    and q in tree_node.node.description.casefold()
                )
                if not (name_match or path_match or desc_match):
                    matches_self = False

            # Match type_filter
            if matches_self and actual_type_filter:
                kind = tree_node.node.node_kind
                res_type = tree_node.node.resource_type
                if actual_type_filter == "workspace":
                    if kind != "workspace":
                        matches_self = False
                elif actual_type_filter == "folder":
                    if kind != "folder":
                        matches_self = False
                elif actual_type_filter == "directory":
                    if not (kind == "resource" and res_type == "directory"):
                        matches_self = False

            # Keep node if it matches itself OR if it has any matched descendants
            if matches_self or filtered_children:
                return TreeNode(tree_node.node, filtered_children)

            return None

        # Apply filtering to all root-level TreeNodes
        filtered_roots = []
        for root in full_tree:
            filtered_root = filter_node(root)
            if filtered_root is not None:
                filtered_roots.append(filtered_root)

        return filtered_roots
