"""Action provider for directory resources."""

from pathtree.actions.base import (
    ResourceAction,
    ResourceActionContext,
    ResourceActionProvider,
    ResourceActionResult,
)
from pathtree.services.node_service import NodeService, NodeServiceError


class DirectoryActionProvider(ResourceActionProvider):
    """Action provider for 'directory' resource types."""

    def __init__(self, node_service: NodeService) -> None:
        """Initialize the DirectoryActionProvider with a NodeService."""
        self._node_service = node_service

    @property
    def resource_type(self) -> str:
        """The supported resource type."""
        return "directory"

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for directory resources."""
        return [
            ResourceAction(
                id="change_directory",
                label="Change Directory",
                description="Change current shell directory to this path",
                is_default=True,
            ),
            ResourceAction(
                id="copy_path",
                label="Copy Path",
                description="Copy directory path to clipboard",
            ),
            ResourceAction(
                id="view_details",
                label="View Details",
                description="Show directory metadata and details",
            ),
        ]

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for directory resources."""
        actions = self.get_available_actions(context)
        return next((a for a in actions if a.is_default), None)

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        if (
            context.node.node_kind != "resource"
            or context.node.resource_type != "directory"
        ):
            return ResourceActionResult(
                success=False,
                error_message="Invalid node type for Directory provider.",
            )

        # Resolve the directory path using either context override or node service
        try:
            if context.resolved_path is not None:
                resolved_path = context.resolved_path
            else:
                resolved_path = str(
                    self._node_service.resolve_node_path(context.node.id).absolute()
                )
        except (NodeServiceError, OSError, ValueError) as e:
            return ResourceActionResult(
                success=False,
                error_message=str(e),
            )

        if action_id == "change_directory":
            if not context.output_path:
                return ResourceActionResult(
                    success=False,
                    error_message=(
                        "No output file specified. "
                        "Activation requires the --output option."
                    ),
                )
            try:
                with open(context.output_path, "w", encoding="utf-8") as f:
                    f.write(resolved_path)
                return ResourceActionResult(
                    success=True,
                    exit_app=True,
                    output_value=resolved_path,
                    message=f"Successfully changed directory to {resolved_path}",
                )
            except (OSError, UnicodeError) as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "copy_path":
            # copy_path execution may return the resolved path as a
            # result object for now. Do not introduce clipboard dependencies.
            return ResourceActionResult(
                success=True,
                exit_app=False,
                output_value=resolved_path,
                message=f"Copied path: {resolved_path}",
            )

        elif action_id == "view_details":
            # view_details may return structured metadata or reuse
            # existing node details.
            metadata = f"Name: {context.node.name}\nPath: {resolved_path}"
            if context.node.description:
                metadata += f"\nDescription: {context.node.description}"
            return ResourceActionResult(
                success=True,
                exit_app=False,
                output_value=metadata,
                message=f"Details for {context.node.name}",
            )

        else:
            return ResourceActionResult(
                success=False,
                error_message=f"Unknown action: {action_id}",
            )
