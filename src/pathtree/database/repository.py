import uuid
from collections.abc import Sequence

from sqlmodel import Session, select

from pathtree.models.node import Node


class NodeRepository:
    """Repository for managing Node persistence.

    Handles all direct CRUD and query operations with SQLModel.
    Keeps business logic completely decoupled from the data layer.
    """

    def __init__(self, session: Session) -> None:
        """Initialize the repository with a database session."""
        self.session = session

    def create(self, node: Node) -> Node:
        """Create a new Node in the database.

        Args:
            node: The Node object to persist.

        Returns:
            The persisted Node object.
        """
        self.session.add(node)
        self.session.commit()
        self.session.refresh(node)
        return node

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
        self.session.add(node)
        self.session.commit()
        self.session.refresh(node)
        return node

    def delete(self, id: uuid.UUID) -> bool:
        """Delete a Node by its UUID.

        Args:
            id: The UUID of the Node to delete.

        Returns:
            True if the Node was deleted, False if not found.
        """
        node = self.get_by_id(id)
        if node:
            self.session.delete(node)
            self.session.commit()
            return True
        return False
