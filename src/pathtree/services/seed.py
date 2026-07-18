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
        node_kind: str,
        resource_type: str | None,
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
            node_kind=node_kind,
            resource_type=resource_type,
            path=path,
            parent_id=parent_id,
            sort_order=sort_order,
        )
        return repository.create(node)

    # Seed top-level workspace nodes (pure containers, path=None)
    home_ws = get_or_create("Home Workspace", "workspace", None, None, None, 1)
    get_or_create("Home", "resource", "directory", str(home_dir), home_ws.id, 1)

    temp_ws = get_or_create("Temporary Directory", "workspace", None, None, None, 2)
    get_or_create("Temp", "resource", "directory", str(temp_dir), temp_ws.id, 1)

    # Seed sub-nodes under Home Workspace only if they exist on the filesystem
    docs_path = home_dir / "Documents"
    if docs_path.is_dir():
        docs_folder = get_or_create("Documents", "folder", None, None, home_ws.id, 2)
        get_or_create(
            "Documents Directory",
            "resource",
            "directory",
            str(docs_path),
            docs_folder.id,
            1,
        )

    downloads_path = home_dir / "Downloads"
    if downloads_path.is_dir():
        downloads_folder = get_or_create(
            "Downloads", "folder", None, None, home_ws.id, 3
        )
        get_or_create(
            "Downloads Directory",
            "resource",
            "directory",
            str(downloads_path),
            downloads_folder.id,
            1,
        )

    project_folder = get_or_create(
        "Current Project", "folder", None, None, home_ws.id, 4
    )
    get_or_create(
        "Project Directory",
        "resource",
        "directory",
        str(Path.cwd()),
        project_folder.id,
        1,
    )

    # Seed sub-nodes under Temp Workspace
    temp_sub_folder = get_or_create(
        "System Temp Sub", "folder", None, None, temp_ws.id, 2
    )
    get_or_create(
        "Sub Temp Directory",
        "resource",
        "directory",
        str(temp_dir),
        temp_sub_folder.id,
        1,
    )
