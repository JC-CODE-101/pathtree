import uuid
from collections.abc import Sequence

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlmodel import Session, select

from pathtree.database.errors import RepositoryError, RepositoryIntegrityError
from pathtree.models.node import Node
from pathtree.models.pin import Pin


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
