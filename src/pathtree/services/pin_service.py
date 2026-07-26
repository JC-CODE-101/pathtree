import uuid
from collections.abc import Sequence

from pathtree.database.repository import NodeRepository, PinRepository
from pathtree.models.pin import Pin


class PinServiceError(Exception):
    """Base exception class for all PinService errors."""


class NonexistentNodeError(PinServiceError):
    """Raised when trying to pin a node that does not exist."""


class DuplicatePinError(PinServiceError):
    """Raised when a node is already pinned."""


class InvalidPositionError(PinServiceError):
    """Raised when a pin position is out of valid range."""


class PinNotFoundError(PinServiceError):
    """Raised when a requested pin does not exist."""


class StalePinReferenceError(PinServiceError):
    """Raised when a pin references a node that no longer exists."""


class PinService:
    """Service layer coordinating Pin business operations."""

    def __init__(
        self, node_repository: NodeRepository, pin_repository: PinRepository
    ) -> None:
        """Initialize PinService with node and pin repositories."""
        self.node_repository = node_repository
        self.pin_repository = pin_repository

    def pin_node(self, node_id: uuid.UUID, custom_label: str | None = None) -> Pin:
        """Pin a node to the global pinned list.

        Args:
            node_id: UUID of the node to pin.
            custom_label: Optional display label override.

        Returns:
            The created Pin object.

        Raises:
            NonexistentNodeError: If node_id does not exist.
            DuplicatePinError: If the node is already pinned.
        """
        node = self.node_repository.get_by_id(node_id)
        if node is None:
            raise NonexistentNodeError(f"Node {node_id} does not exist.")

        existing = self.pin_repository.get_by_node_id(node_id)
        if existing is not None:
            raise DuplicatePinError(f"Node {node_id} is already pinned.")

        max_pos = self.pin_repository.get_max_position()
        next_pos = max_pos + 1

        pin = Pin(
            node_id=node_id,
            position=next_pos,
            custom_label=custom_label,
        )
        return self.pin_repository.create(pin)

    def unpin_node(self, node_id: uuid.UUID) -> bool:
        """Unpin a node and compact remaining pin positions.

        Args:
            node_id: UUID of the node to unpin.

        Returns:
            True if successfully unpinned, False otherwise.

        Raises:
            PinNotFoundError: If the node is not currently pinned.
        """
        pin = self.pin_repository.get_by_node_id(node_id)
        if pin is None:
            raise PinNotFoundError(f"Node {node_id} is not pinned.")

        deleted = self.pin_repository.delete(pin.id)
        if deleted:
            self._compact_positions()
        return deleted

    def list_pins(self) -> Sequence[Pin]:
        """List all pins sorted by position.

        Returns:
            A list of Pin objects.
        """
        return self.pin_repository.list_all()

    def get_pin_by_position(self, position: int) -> Pin:
        """Retrieve a pin by its numeric position.

        Args:
            position: The numeric position (1-based).

        Returns:
            The Pin object.

        Raises:
            InvalidPositionError: If the position is out of bounds or invalid.
            StalePinReferenceError: If the pin references a non-existent node.
        """
        if position < 1:
            raise InvalidPositionError(f"Position {position} is invalid.")

        pins = self.list_pins()
        if position > len(pins):
            raise InvalidPositionError(f"No pin found at position {position}.")

        pin = pins[position - 1]

        # Verify target node exists
        node = self.node_repository.get_by_id(pin.node_id)
        if node is None:
            raise StalePinReferenceError(
                f"Pin references nonexistent node {pin.node_id}."
            )

        return pin

    def reorder_pin(self, pin_id: uuid.UUID, new_position: int) -> Pin:
        """Reorder a pin to a new position, shifting other pins contiguous.

        Args:
            pin_id: The UUID of the Pin to reorder.
            new_position: The target position (1-based).

        Returns:
            The updated Pin object.

        Raises:
            PinNotFoundError: If the pin does not exist.
            InvalidPositionError: If the target position is out of valid range.
        """
        pin = self.pin_repository.get_by_id(pin_id)
        if pin is None:
            raise PinNotFoundError(f"Pin {pin_id} does not exist.")

        pins = self.list_pins()
        n = len(pins)
        if new_position < 1 or new_position > n:
            raise InvalidPositionError(
                f"Position {new_position} is out of valid range (1-{n})."
            )

        orig_position = pin.position
        if orig_position == new_position:
            return pin

        # Update positions of affected pins
        if orig_position < new_position:
            # Shift down pins between orig_position + 1 and new_position
            for p in pins:
                if orig_position < p.position <= new_position:
                    p.position -= 1
                    self.pin_repository.update(p)
        else:
            # Shift up pins between new_position and orig_position - 1
            for p in pins:
                if new_position <= p.position < orig_position:
                    p.position += 1
                    self.pin_repository.update(p)

        pin.position = new_position
        return self.pin_repository.update(pin)

    def is_pinned(self, node_id: uuid.UUID) -> bool:
        """Check if a node is currently pinned.

        Args:
            node_id: UUID of the node.

        Returns:
            True if pinned, False otherwise.
        """
        return self.pin_repository.get_by_node_id(node_id) is not None

    def _compact_positions(self) -> None:
        """Re-index all pins to ensure contiguous positions starting at 1."""
        pins = self.pin_repository.list_all()
        for idx, pin in enumerate(pins):
            expected_pos = idx + 1
            if pin.position != expected_pos:
                pin.position = expected_pos
                self.pin_repository.update(pin)
