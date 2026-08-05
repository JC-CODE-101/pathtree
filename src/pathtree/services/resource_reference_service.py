import uuid

from pathtree.database.repository import ResourceReferenceRepository
from pathtree.models.node import Node
from pathtree.models.resource_reference import ResourceReference
from pathtree.services.node_service import (
    NodeNotFoundError,
    NodeService,
    ValidationError,
)


class ResourceReferenceService:
    """Service layer managing Resource References."""

    def __init__(
        self,
        node_service: NodeService,
        repository: ResourceReferenceRepository,
    ) -> None:
        """Initialize the ResourceReferenceService."""
        self.node_service = node_service
        self.repository = repository

    def create_reference(
        self,
        original_node_id: uuid.UUID,
        destination_parent_id: uuid.UUID,
        custom_name: str | None = None,
    ) -> ResourceReference:
        """Create a new resource reference node and database record."""
        # 1. Verify original node exists
        original_node = self.node_service.get_node(original_node_id)
        if not original_node:
            raise NodeNotFoundError(f"Original node '{original_node_id}' not found.")

        # Real resource check: Reference can only point to a real resource (or compatible node)
        if (
            original_node.node_kind != "resource"
            or original_node.resource_type == "reference"
        ):
            raise ValidationError("References can only point to real resources.")

        # Use provided custom_name or fall back to original name
        name = custom_name.strip() if custom_name else original_node.name

        # 2. Create the reference node in the tree under destination_parent_id
        # Note: validate_node will enforce node_kind="resource", resource_type="reference"
        ref_node = self.node_service.create_node(
            name=name,
            node_kind="resource",
            resource_type="reference",
            parent_id=destination_parent_id,
        )

        # 3. Create ResourceReference record
        ref = ResourceReference(
            reference_node_id=ref_node.id,
            original_node_id=original_node.id,
        )
        return self.repository.create(ref)

    def get_reference_by_node_id(
        self, reference_node_id: uuid.UUID
    ) -> ResourceReference | None:
        """Retrieve the ResourceReference record associated with a reference Node ID."""
        return self.repository.get_by_reference_node_id(reference_node_id)

    def get_original_node(self, reference_node_id: uuid.UUID) -> Node | None:
        """Get the original Node associated with a reference, or None if broken."""
        ref = self.get_reference_by_node_id(reference_node_id)
        if not ref or ref.original_node_id is None:
            return None
        return self.node_service.get_node(ref.original_node_id)

    def is_broken(self, reference_node_id: uuid.UUID) -> bool:
        """Determine if a reference is broken (original node missing or null)."""
        ref = self.get_reference_by_node_id(reference_node_id)
        if not ref or ref.original_node_id is None:
            return True
        orig = self.node_service.get_node(ref.original_node_id)
        return orig is None

    def reconnect_reference(
        self, reference_node_id: uuid.UUID, new_original_node_id: uuid.UUID
    ) -> ResourceReference:
        """Reconnect a reference to a new original node."""
        ref = self.get_reference_by_node_id(reference_node_id)
        if not ref:
            raise ValidationError("Reference record not found.")

        new_orig = self.node_service.get_node(new_original_node_id)
        if not new_orig:
            raise NodeNotFoundError(
                f"New original node '{new_original_node_id}' not found."
            )

        if new_orig.node_kind != "resource" or new_orig.resource_type == "reference":
            raise ValidationError("References can only point to real resources.")

        ref.original_node_id = new_original_node_id
        return self.repository.update(ref)

    def duplicate_reference(self, reference_node_id: uuid.UUID) -> Node:
        """Duplicate a reference node and its DB record under the same parent."""
        ref = self.get_reference_by_node_id(reference_node_id)
        if not ref:
            raise ValidationError("Reference not found.")

        ref_node = self.node_service.get_node(reference_node_id)
        if not ref_node:
            raise ValidationError("Reference node not found.")

        copied_name = f"{ref_node.name} Copy"
        base_name = copied_name
        counter = 1
        while self.node_service.repository.has_sibling_with_name(
            ref_node.parent_id, copied_name
        ):
            copied_name = f"{base_name} ({counter})"
            counter += 1

        new_node = self.node_service.create_node(
            name=copied_name,
            node_kind="resource",
            resource_type="reference",
            parent_id=ref_node.parent_id,
            description=ref_node.description,
            icon=ref_node.icon,
        )

        new_ref = ResourceReference(
            reference_node_id=new_node.id,
            original_node_id=ref.original_node_id,
        )
        self.repository.create(new_ref)
        return new_node

    def delete_reference(self, reference_node_id: uuid.UUID) -> bool:
        """Delete the reference node. Will cascade delete the ResourceReference entry."""
        # delete_node handles cascades and deleting from DB cleanly
        return self.node_service.delete_node(reference_node_id, recursive=True)
