import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from pathtree.database.errors import RepositoryError, RepositoryIntegrityError
from pathtree.models.launch_profile import LaunchProfile
from pathtree.models.multi_launcher import MultiLauncher, MultiLauncherItem
from pathtree.models.node import Node
from pathtree.models.pin import Pin
from pathtree.models.resource_reference import ResourceReference
from pathtree.models.workspace_view_settings import WorkspaceViewSettings


class RepositoryCycleError(Exception):
    """Raised when a parent-child cycle is detected in the database."""


class NodeRepository:
    """Repository for managing Node persistence.

    Handles all direct CRUD and query operations with SQLModel.
    Keeps business logic completely decoupled from the data layer.
    """

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def _set_legacy_node_type(self, node: Node) -> None:
        """Map canonical types to legacy_node_type for DB compatibility."""
        if node.node_kind == "workspace":
            node.legacy_node_type = "Workspace"
        elif node.node_kind == "folder":
            node.legacy_node_type = "Folder"
        elif node.node_kind == "resource" and node.resource_type == "directory":
            node.legacy_node_type = "Folder"
        else:
            node.legacy_node_type = "Folder"

    def create(self, node: Node) -> Node:
        """Create a new Node in the database.

        Args:
            node: The Node object to persist.

        Returns:
            The persisted Node object.
        """
        self._set_legacy_node_type(node)
        try:
            self.session.add(node)
            self.session.commit()
            self.session.refresh(node)
            return node
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database persistence violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database persistence failed: {e}") from e

    def get_by_id(self, id: uuid.UUID) -> Node | None:
        """Retrieve a Node by its UUID.

        Args:
            id: The UUID of the Node.

        Returns:
            The Node object if found, otherwise None.
        """
        return self.session.get(Node, id)

    def list_all(self) -> Sequence[Node]:
        """Retrieve all Node records sorted by sort_order and creation date.

        Returns:
            A list of all Nodes in the database.
        """
        statement = select(Node).order_by(Node.sort_order, Node.created_at)
        return self.session.exec(statement).all()

    def list_children(self, parent_id: uuid.UUID | None) -> Sequence[Node]:
        """Retrieve children Nodes of a given parent node sorted by sort_order.

        Args:
            parent_id: The UUID of the parent, or None for root level.

        Returns:
            A list of child Nodes.
        """
        statement = (
            select(Node)
            .where(Node.parent_id == parent_id)
            .order_by(Node.sort_order, Node.created_at)
        )
        return self.session.exec(statement).all()

    def update(self, node: Node) -> Node:
        """Update an existing Node in the database.

        Args:
            node: The modified Node object.

        Returns:
            The updated Node object.
        """
        from datetime import UTC, datetime

        node.updated_at = datetime.now(UTC)
        self._set_legacy_node_type(node)
        try:
            self.session.add(node)
            self.session.commit()
            self.session.refresh(node)
            return node
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database update violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database update failed: {e}") from e

    def delete(self, id: uuid.UUID) -> bool:
        """Delete a Node by its UUID.

        Args:
            id: The UUID of the Node to delete.

        Returns:
            True if the Node was deleted, False if not found.
        """
        node = self.get_by_id(id)
        if node:
            try:
                self.session.delete(node)
                self.session.commit()
                return True
            except IntegrityError as e:
                self.session.rollback()
                raise RepositoryIntegrityError(
                    f"Database deletion violated integrity: {e}"
                ) from e
            except SQLAlchemyError as e:
                self.session.rollback()
                raise RepositoryError(f"Database deletion failed: {e}") from e
        return False

    def get_descendants(self, node_id: uuid.UUID) -> list[Node]:
        """Fetch all descendants of node_id recursively."""
        descendants = []
        queue = [node_id]
        visited = {node_id}
        while queue:
            curr_id = queue.pop(0)
            statement = select(Node).where(Node.parent_id == curr_id)
            children = self.session.exec(statement).all()
            for child in children:
                if child.id in visited:
                    raise RepositoryCycleError(
                        f"Cycle detected in parent hierarchy: "
                        f"{child.id} is already visited."
                    )
                visited.add(child.id)
                descendants.append(child)
                queue.append(child.id)
        return descendants

    def delete_recursive(self, node_id: uuid.UUID) -> int:
        """Atomically delete node_id and all its descendants.

        Returns the number of descendants deleted.
        """
        descendants = self.get_descendants(node_id)
        try:
            # Delete associated pins first to prevent FOREIGN KEY constraint failures
            from sqlmodel import delete

            node_ids_to_delete = [node_id] + [d.id for d in descendants]
            pin_del_stmt = delete(Pin).where(Pin.node_id.in_(node_ids_to_delete))
            self.session.exec(pin_del_stmt)
            self.session.flush()

            for desc in reversed(descendants):
                self.session.delete(desc)
                self.session.flush()
            node = self.session.get(Node, node_id)
            if node:
                self.session.delete(node)
                self.session.flush()
            self.session.commit()
            self.session.expire_all()
            return len(descendants)
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database recursive deletion violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database recursive deletion failed: {e}") from e

    def has_sibling_with_name(
        self,
        parent_id: uuid.UUID | None,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        """Check if any sibling under parent_id has the same normalized name.

        Normalization rule: strip and casefold.
        """
        statement = select(Node).where(Node.parent_id == parent_id)
        siblings = self.session.exec(statement).all()
        normalized_target = name.strip().casefold()
        for sib in siblings:
            if exclude_id is not None and sib.id == exclude_id:
                continue
            if sib.name.strip().casefold() == normalized_target:
                return True
        return False


class PinRepository:
    """Repository for managing Pin persistence.

    Handles CRUD operations and queries on the pins table.
    """

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, pin: Pin) -> Pin:
        """Create a new Pin in the database."""
        try:
            self.session.add(pin)
            self.session.commit()
            self.session.refresh(pin)
            return pin
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database persistence violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database persistence failed: {e}") from e

    def get_by_id(self, id: uuid.UUID) -> Pin | None:
        """Retrieve a Pin by its UUID."""
        return self.session.get(Pin, id)

    def get_by_node_id(self, node_id: uuid.UUID) -> Pin | None:
        """Retrieve a Pin by Node UUID."""
        statement = select(Pin).where(Pin.node_id == node_id)
        return self.session.exec(statement).first()

    def list_all(self) -> Sequence[Pin]:
        """Retrieve all Pin records sorted by position."""
        statement = select(Pin).order_by(Pin.position)
        return self.session.exec(statement).all()

    def update(self, pin: Pin) -> Pin:
        """Update an existing Pin in the database."""
        from datetime import UTC, datetime

        pin.updated_at = datetime.now(UTC)
        try:
            self.session.add(pin)
            self.session.commit()
            self.session.refresh(pin)
            return pin
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database update violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database update failed: {e}") from e

    def delete(self, id: uuid.UUID) -> bool:
        """Delete a Pin by its UUID."""
        pin = self.get_by_id(id)
        if pin:
            try:
                self.session.delete(pin)
                self.session.commit()
                return True
            except IntegrityError as e:
                self.session.rollback()
                raise RepositoryIntegrityError(
                    f"Database deletion violated integrity: {e}"
                ) from e
            except SQLAlchemyError as e:
                self.session.rollback()
                raise RepositoryError(f"Database deletion failed: {e}") from e
        return False

    def delete_by_node_id(self, node_id: uuid.UUID) -> bool:
        """Delete a Pin associated with a Node UUID."""
        pin = self.get_by_node_id(node_id)
        if pin:
            return self.delete(pin.id)
        return False

    def get_max_position(self) -> int:
        """Get the current maximum position among all pins, or 0 if empty."""
        statement = select(Pin).order_by(Pin.position.desc())
        pin = self.session.exec(statement).first()
        return pin.position if pin else 0


class MultiLauncherRepository:
    """Repository for managing MultiLauncher persistence."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, launcher: MultiLauncher) -> MultiLauncher:
        """Create a new MultiLauncher in the database."""
        try:
            self.session.add(launcher)
            self.session.commit()
            self.session.refresh(launcher)
            return launcher
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database persistence violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database persistence failed: {e}") from e

    def get_by_id(self, id: uuid.UUID) -> MultiLauncher | None:
        """Retrieve a MultiLauncher by its UUID."""
        return self.session.get(MultiLauncher, id)

    def get_by_launcher_node_id(
        self, launcher_node_id: uuid.UUID
    ) -> MultiLauncher | None:
        """Retrieve a MultiLauncher by its node UUID."""
        statement = select(MultiLauncher).where(
            MultiLauncher.launcher_node_id == launcher_node_id
        )
        return self.session.exec(statement).first()

    def list_all(self) -> Sequence[MultiLauncher]:
        """Retrieve all MultiLauncher records."""
        statement = select(MultiLauncher)
        return self.session.exec(statement).all()

    def list_by_workspace(self, workspace_id: uuid.UUID) -> Sequence[MultiLauncher]:
        """Retrieve all MultiLauncher records belonging to a workspace."""
        statement = select(MultiLauncher).where(
            MultiLauncher.workspace_id == workspace_id
        )
        return self.session.exec(statement).all()

    def update(self, launcher: MultiLauncher) -> MultiLauncher:
        """Update an existing MultiLauncher in the database."""
        from datetime import UTC, datetime

        launcher.updated_at = datetime.now(UTC)
        try:
            self.session.add(launcher)
            self.session.commit()
            self.session.refresh(launcher)
            return launcher
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database update violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database update failed: {e}") from e

    def delete(self, id: uuid.UUID) -> bool:
        """Delete a MultiLauncher by its UUID."""
        launcher = self.get_by_id(id)
        if launcher:
            try:
                self.session.delete(launcher)
                self.session.commit()
                return True
            except IntegrityError as e:
                self.session.rollback()
                raise RepositoryIntegrityError(
                    f"Database deletion violated integrity: {e}"
                ) from e
            except SQLAlchemyError as e:
                self.session.rollback()
                raise RepositoryError(f"Database deletion failed: {e}") from e
        return False

    def create_item(self, item: MultiLauncherItem) -> MultiLauncherItem:
        """Create a new MultiLauncherItem in the database."""
        try:
            self.session.add(item)
            self.session.commit()
            self.session.refresh(item)
            return item
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database persistence violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database persistence failed: {e}") from e

    def get_item_by_id(self, item_id: uuid.UUID) -> MultiLauncherItem | None:
        """Retrieve a MultiLauncherItem by its UUID."""
        return self.session.get(MultiLauncherItem, item_id)

    def list_items_for_launcher(
        self, launcher_id: uuid.UUID
    ) -> list[MultiLauncherItem]:
        """Retrieve all items for a MultiLauncher sorted by position."""
        statement = (
            select(MultiLauncherItem)
            .where(MultiLauncherItem.multi_launcher_id == launcher_id)
            .order_by(MultiLauncherItem.position)
        )
        return list(self.session.exec(statement).all())

    def update_item(self, item: MultiLauncherItem) -> MultiLauncherItem:
        """Update a MultiLauncherItem."""
        try:
            self.session.add(item)
            self.session.commit()
            self.session.refresh(item)
            return item
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database update violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database update failed: {e}") from e

    def delete_item(self, item_id: uuid.UUID) -> bool:
        """Delete a MultiLauncherItem by ID."""
        item = self.get_item_by_id(item_id)
        if item:
            try:
                self.session.delete(item)
                self.session.commit()
                return True
            except IntegrityError as e:
                self.session.rollback()
                raise RepositoryIntegrityError(
                    f"Database deletion violated integrity: {e}"
                ) from e
            except SQLAlchemyError as e:
                self.session.rollback()
                raise RepositoryError(f"Database deletion failed: {e}") from e
        return False


class LaunchProfileRepository:
    """Repository for managing LaunchProfile persistence."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, profile: LaunchProfile) -> LaunchProfile:
        """Create a new LaunchProfile in the database."""
        try:
            self.session.add(profile)
            self.session.commit()
            self.session.refresh(profile)
            return profile
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database persistence violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database persistence failed: {e}") from e

    def get_by_id(self, id: uuid.UUID) -> LaunchProfile | None:
        """Retrieve a LaunchProfile by its UUID."""
        return self.session.get(LaunchProfile, id)

    def get_by_profile_node_id(
        self, profile_node_id: uuid.UUID
    ) -> LaunchProfile | None:
        """Retrieve a LaunchProfile by its Profile Node UUID."""
        statement = select(LaunchProfile).where(
            LaunchProfile.profile_node_id == profile_node_id
        )
        return self.session.exec(statement).first()

    def list_all(self) -> Sequence[LaunchProfile]:
        """Retrieve all LaunchProfile records."""
        statement = select(LaunchProfile)
        return self.session.exec(statement).all()

    def list_by_workspace(self, workspace_id: uuid.UUID) -> Sequence[LaunchProfile]:
        """Retrieve all LaunchProfile records belonging to a workspace."""
        statement = select(LaunchProfile).where(
            LaunchProfile.workspace_id == workspace_id
        )
        return self.session.exec(statement).all()

    def list_by_target(self, target_node_id: uuid.UUID) -> Sequence[LaunchProfile]:
        """Retrieve all LaunchProfile records connected to a target node."""
        statement = select(LaunchProfile).where(
            LaunchProfile.target_node_id == target_node_id
        )
        return self.session.exec(statement).all()

    def list_by_working_directory(
        self, working_directory_node_id: uuid.UUID
    ) -> Sequence[LaunchProfile]:
        """Retrieve all LaunchProfile records using a working directory."""
        statement = select(LaunchProfile).where(
            LaunchProfile.working_directory_node_id == working_directory_node_id
        )
        return self.session.exec(statement).all()

    def update(self, profile: LaunchProfile) -> LaunchProfile:
        """Update an existing LaunchProfile in the database."""
        from datetime import UTC, datetime

        profile.updated_at = datetime.now(UTC)
        try:
            self.session.add(profile)
            self.session.commit()
            self.session.refresh(profile)
            return profile
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database update violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database update failed: {e}") from e

    def delete(self, id: uuid.UUID) -> bool:
        """Delete a LaunchProfile by its UUID."""
        profile = self.get_by_id(id)
        if profile:
            try:
                self.session.delete(profile)
                self.session.commit()
                return True
            except IntegrityError as e:
                self.session.rollback()
                raise RepositoryIntegrityError(
                    f"Database deletion violated integrity: {e}"
                ) from e
            except SQLAlchemyError as e:
                self.session.rollback()
                raise RepositoryError(f"Database deletion failed: {e}") from e
        return False


class ResourceReferenceRepository:
    """Repository for managing ResourceReference persistence."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, ref: ResourceReference) -> ResourceReference:
        """Create a new ResourceReference in the database."""
        try:
            self.session.add(ref)
            self.session.commit()
            self.session.refresh(ref)
            return ref
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database persistence violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database persistence failed: {e}") from e

    def get_by_id(self, id: uuid.UUID) -> ResourceReference | None:
        """Retrieve a ResourceReference by its UUID."""
        return self.session.get(ResourceReference, id)

    def get_by_reference_node_id(
        self, reference_node_id: uuid.UUID
    ) -> ResourceReference | None:
        """Retrieve a ResourceReference by its Reference Node UUID."""
        statement = select(ResourceReference).where(
            ResourceReference.reference_node_id == reference_node_id
        )
        return self.session.exec(statement).first()

    def list_all(self) -> Sequence[ResourceReference]:
        """Retrieve all ResourceReference records."""
        statement = select(ResourceReference)
        return self.session.exec(statement).all()

    def update(self, ref: ResourceReference) -> ResourceReference:
        """Update an existing ResourceReference in the database."""
        from datetime import UTC, datetime

        ref.updated_at = datetime.now(UTC)
        try:
            self.session.add(ref)
            self.session.commit()
            self.session.refresh(ref)
            return ref
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database update violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database update failed: {e}") from e

    def delete(self, id: uuid.UUID) -> bool:
        """Delete a ResourceReference by its UUID."""
        ref = self.get_by_id(id)
        if ref:
            try:
                self.session.delete(ref)
                self.session.commit()
                return True
            except IntegrityError as e:
                self.session.rollback()
                raise RepositoryIntegrityError(
                    f"Database deletion violated integrity: {e}"
                ) from e
            except SQLAlchemyError as e:
                self.session.rollback()
                raise RepositoryError(f"Database deletion failed: {e}") from e
        return False


class WorkspaceViewSettingsRepository:
    """Repository for managing WorkspaceViewSettings persistence."""

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, settings: WorkspaceViewSettings) -> WorkspaceViewSettings:
        """Create a new WorkspaceViewSettings in the database."""
        try:
            self.session.add(settings)
            self.session.commit()
            self.session.refresh(settings)
            return settings
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database persistence violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database persistence failed: {e}") from e

    def get_by_id(self, id: uuid.UUID) -> WorkspaceViewSettings | None:
        """Retrieve a WorkspaceViewSettings by its UUID."""
        return self.session.get(WorkspaceViewSettings, id)

    def get_by_workspace_id(
        self, workspace_id: uuid.UUID
    ) -> WorkspaceViewSettings | None:
        """Retrieve a WorkspaceViewSettings by Workspace UUID."""
        statement = select(WorkspaceViewSettings).where(
            WorkspaceViewSettings.workspace_id == workspace_id
        )
        return self.session.exec(statement).first()

    def update(self, settings: WorkspaceViewSettings) -> WorkspaceViewSettings:
        """Update an existing WorkspaceViewSettings in the database."""
        from datetime import UTC, datetime

        settings.updated_at = datetime.now(UTC)
        try:
            self.session.add(settings)
            self.session.commit()
            self.session.refresh(settings)
            return settings
        except IntegrityError as e:
            self.session.rollback()
            raise RepositoryIntegrityError(
                f"Database update violated integrity: {e}"
            ) from e
        except SQLAlchemyError as e:
            self.session.rollback()
            raise RepositoryError(f"Database update failed: {e}") from e

    def delete(self, id: uuid.UUID) -> bool:
        """Delete a WorkspaceViewSettings by its UUID."""
        settings = self.get_by_id(id)
        if settings:
            try:
                self.session.delete(settings)
                self.session.commit()
                return True
            except IntegrityError as e:
                self.session.rollback()
                raise RepositoryIntegrityError(
                    f"Database deletion violated integrity: {e}"
                ) from e
            except SQLAlchemyError as e:
                self.session.rollback()
                raise RepositoryError(f"Database deletion failed: {e}") from e
        return False

    def delete_by_workspace_id(self, workspace_id: uuid.UUID) -> bool:
        """Delete a WorkspaceViewSettings associated with a Workspace UUID."""
        settings = self.get_by_workspace_id(workspace_id)
        if settings:
            return self.delete(settings.id)
        return False
