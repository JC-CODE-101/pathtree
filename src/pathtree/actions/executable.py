"""Action provider for executable resources."""

from pathlib import Path

from pathtree.actions.base import (
    ResourceAction,
    ResourceActionContext,
    ResourceActionProvider,
    ResourceActionResult,
    ResourceActionResultTarget,
)
from pathtree.services.node_service import NodeService, NodeServiceError
from pathtree.utils.launcher import LaunchError, PlatformLauncher


class ExecutableActionProvider(ResourceActionProvider):
    """Action provider for 'executable' resource types."""

    def __init__(self, node_service: NodeService) -> None:
        """Initialize the ExecutableActionProvider with a NodeService."""
        self._node_service = node_service

    @property
    def resource_type(self) -> str:
        """The supported resource type."""
        return "executable"

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for executable resources."""
        return [
            ResourceAction(
                id="launch",
                label="Launch",
                description="Launch this executable safely",
                is_default=True,
            ),
            ResourceAction(
                id="open_containing_folder",
                label="Open Containing Folder",
                description="Open the folder containing this executable",
            ),
            ResourceAction(
                id="copy_path",
                label="Copy Path",
                description="Copy executable path to clipboard",
            ),
            ResourceAction(
                id="view_details",
                label="View Details",
                description="Show executable metadata and details",
            ),
        ]

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for executable resources."""
        actions = self.get_available_actions(context)
        return next((a for a in actions if a.is_default), None)

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        if (
            context.node.node_kind != "resource"
            or context.node.resource_type != "executable"
        ):
            return ResourceActionResult(
                success=False,
                error_message="Invalid node type for Executable provider.",
            )

        # Resolve path
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

        path_obj = Path(resolved_path)

        if action_id == "launch":
            # Validate executable resources before creation, editing and activation
            try:
                if not resolved_path:
                    raise ValueError("Executable path cannot be empty.")
                if not path_obj.exists():
                    raise FileNotFoundError(
                        f"Executable path '{resolved_path}' does not exist."
                    )
                if not path_obj.is_file():
                    raise IsADirectoryError(
                        f"Executable path '{resolved_path}' is a directory."
                    )
                self._node_service.validate_executable_path(path_obj)
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

            argv = [resolved_path]
            res = PlatformLauncher.launch_process(argv, cwd=path_obj.parent)
            if not res.success:
                return ResourceActionResult(
                    success=False,
                    error_message=res.error_message or "Process launch failed.",
                )

            return ResourceActionResult(
                success=True,
                exit_app=False,
                message=f"Launched executable: {resolved_path}",
                target=ResourceActionResultTarget.NOTIFICATION,
            )

        elif action_id == "open_containing_folder":
            try:
                if not resolved_path:
                    raise ValueError("Executable path cannot be empty.")
                parent_dir_obj = path_obj.parent
                if not parent_dir_obj.exists():
                    raise FileNotFoundError(
                        f"Containing folder '{parent_dir_obj}' does not exist."
                    )
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

            parent_dir = str(parent_dir_obj.absolute())
            try:
                PlatformLauncher.open_path(parent_dir)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    message=f"Opened containing folder: {parent_dir}",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except LaunchError as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "copy_path":
            try:
                PlatformLauncher.copy_to_clipboard(resolved_path)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    output_value=f"Path: {resolved_path}",
                    message=f"Copied path to clipboard: {resolved_path}",
                    target=ResourceActionResultTarget.DETAILS,
                )
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=f"Clipboard error: {e}",
                )

        elif action_id == "view_details":
            try:
                size = path_obj.stat().st_size
                size_str = f"{size} bytes"
                suffix_str = path_obj.suffix or "None"
            except OSError as e:
                size_str = f"Error reading size ({e})"
                suffix_str = "Unknown"

            metadata = (
                f"Name: {context.node.name}\n"
                f"Resource Type: executable\n"
                f"Full Path: {resolved_path}\n"
                f"Size: {size_str}\n"
                f"Extension: {suffix_str}"
            )
            if context.node.description:
                metadata += f"\nDescription: {context.node.description}"

            return ResourceActionResult(
                success=True,
                exit_app=False,
                output_value=metadata,
                message=f"Details for {context.node.name}",
                target=ResourceActionResultTarget.DETAILS,
            )

        else:
            return ResourceActionResult(
                success=False,
                error_message=f"Unknown action: {action_id}",
            )
