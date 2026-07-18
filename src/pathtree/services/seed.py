import tempfile
import uuid
from pathlib import Path

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node


def seed_development_data(repository: NodeRepository) -> None:
    """Idempotently seed development data into the database using safe paths.

    Checks for existing nodes under the same parent with the same name before
    creating to prevent duplicates on repeated execution.
    """
    home_dir = Path.home()
    temp_dir = Path(tempfile.gettempdir())

    def get_or_create(
        name: str,
        node_type: str,
        path: str | None,
        parent_id: uuid.UUID | None,
        sort_order: int,
    ) -> Node:
        # Search existing children of parent_id
        children = repository.list_children(parent_id)
        for child in children:
            if child.name == name:
                return child

        # If not found, create and return
        node = Node(
            name=name,
            node_type=node_type,
            path=path,
            parent_id=parent_id,
            sort_order=sort_order,
        )
        return repository.create(node)

    # Seed top-level workspace nodes
    home_ws = get_or_create("Home Workspace", "Workspace", str(home_dir), None, 1)
    temp_ws = get_or_create("Temporary Directory", "Workspace", str(temp_dir), None, 2)

    # Seed sub-nodes under Home Workspace
    get_or_create("Documents", "Folder", str(home_dir / "Documents"), home_ws.id, 1)
    get_or_create("Downloads", "Folder", str(home_dir / "Downloads"), home_ws.id, 2)
    get_or_create("Current Project", "Folder", str(Path.cwd()), home_ws.id, 3)

    # Seed sub-nodes under Temp Workspace
    get_or_create("System Temp Sub", "Folder", str(temp_dir), temp_ws.id, 1)
