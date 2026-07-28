"""Action provider for Resource References."""

from pathtree.actions.base import (
    ResourceAction,
    ResourceActionContext,
    ResourceActionProvider,
    ResourceActionResult,
    ResourceActionResultTarget,
)
from pathtree.services.node_service import NodeService


class ReferenceActionProvider(ResourceActionProvider):
    """Action provider for 'reference' resource types."""

    def __init__(self, node_service: NodeService) -> None:
        """Initialize the ReferenceActionProvider with a NodeService."""
        self._node_service = node_service

    @property
    def _ref_service(self):
        if not hasattr(self, "_ref_service_lazy"):
            from pathtree.database.repository import ResourceReferenceRepository
            from pathtree.services.resource_reference_service import (
                ResourceReferenceService,
            )

            ref_repo = ResourceReferenceRepository(
                self._node_service.repository.session
            )
            self._ref_service_lazy = ResourceReferenceService(
                self._node_service, ref_repo
            )
        return self._ref_service_lazy

    @property
    def resource_type(self) -> str:
        """The supported resource type."""
        return "reference"

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for reference resources."""
        is_broken = self._ref_service.is_broken(context.node.id)

        if is_broken:
            return [
                ResourceAction(
                    id="reconnect",
                    label="Reconnect Reference",
                    description="Reconnect this broken reference to a real resource",
                ),
                ResourceAction(
                    id="locate_original",
                    label="Locate Original",
                    description="Locate original resource in the tree",
                    is_enabled=False,
                ),
                ResourceAction(
                    id="delete_reference",
                    label="Delete Reference",
                    description="Delete this reference node",
                ),
            ]

        return [
            ResourceAction(
                id="open",
                label="Open",
                description="Open/Execute the original resource",
                is_default=True,
            ),
            ResourceAction(
                id="locate_original",
                label="Locate Original",
                description="Locate original resource in the tree",
            ),
            ResourceAction(
                id="rename_reference",
                label="Rename Reference",
                description="Rename this reference node",
            ),
            ResourceAction(
                id="move_reference",
                label="Move Reference",
                description="Move this reference to another folder",
            ),
            ResourceAction(
                id="duplicate_reference",
                label="Duplicate Reference",
                description="Create a copy of this reference",
            ),
            ResourceAction(
                id="copy_reference_to_workspace",
                label="Copy Reference to Workspace",
                description="Copy this reference to another workspace",
            ),
            ResourceAction(
                id="move_reference_to_workspace",
                label="Move Reference to Workspace",
                description="Move this reference to another workspace",
            ),
            ResourceAction(
                id="delete_reference",
                label="Delete Reference",
                description="Delete this reference",
            ),
        ]

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for reference resources."""
        actions = self.get_available_actions(context)
        return next((a for a in actions if a.is_default), None)

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        if (
            context.node.node_kind != "resource"
            or context.node.resource_type != "reference"
        ):
            return ResourceActionResult(
                success=False,
                error_message="Invalid node type for Reference provider.",
            )

        ref = self._ref_service.get_reference_by_node_id(context.node.id)
        if not ref:
            return ResourceActionResult(
                success=False,
                error_message="Reference record not found.",
            )

        if action_id == "open":
            orig_node = self._ref_service.get_original_node(context.node.id)
            if not orig_node:
                return ResourceActionResult(
                    success=False,
                    error_message="Reference is broken.",
                )
            # We return success with original node's ID in output_value so MainScreen can execute it
            return ResourceActionResult(
                success=True,
                output_value=orig_node.id,
                target=ResourceActionResultTarget.NONE,
            )

        elif action_id == "locate_original":
            orig_node = self._ref_service.get_original_node(context.node.id)
            if not orig_node:
                return ResourceActionResult(
                    success=False,
                    error_message="Reference is broken.",
                )
            return ResourceActionResult(
                success=True,
                output_value=orig_node.id,
                target=ResourceActionResultTarget.NONE,
            )

        elif action_id in (
            "rename_reference",
            "move_reference",
            "reconnect",
            "copy_reference_to_workspace",
            "move_reference_to_workspace",
        ):
            # Handled directly by TUI screens/dialogs
            return ResourceActionResult(
                success=True,
                target=ResourceActionResultTarget.NONE,
            )

        elif action_id == "duplicate_reference":
            try:
                new_node = self._ref_service.duplicate_reference(context.node.id)
                return ResourceActionResult(
                    success=True,
                    message=f"Duplicated reference '{context.node.name}' to '{new_node.name}'",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "delete_reference":
            try:
                self._ref_service.delete_reference(context.node.id)
                return ResourceActionResult(
                    success=True,
                    message=f"Deleted reference '{context.node.name}'",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        return ResourceActionResult(
            success=False,
            error_message=f"Unknown action: {action_id}",
        )
