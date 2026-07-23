"""Action provider for file resources."""

import os
import shlex
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


class FileActionProvider(ResourceActionProvider):
    """Action provider for 'file' resource types."""

    def __init__(self, node_service: NodeService) -> None:
        """Initialize the FileActionProvider with a NodeService."""
        self._node_service = node_service

    @property
    def resource_type(self) -> str:
        """The supported resource type."""
        return "file"

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for file resources."""
        return [
            ResourceAction(
                id="open_file",
                label="Open File",
                description="Open this file with the system default application",
                is_default=True,
            ),
            ResourceAction(
                id="edit_file",
                label="Edit File",
                description="Open this file in your configured editor",
            ),
            ResourceAction(
                id="copy_path",
                label="Copy Path",
                description="Copy file path to details panel",
            ),
            ResourceAction(
                id="view_details",
                label="View Details",
                description="Show file metadata and details",
            ),
        ]

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for file resources."""
        actions = self.get_available_actions(context)
        return next((a for a in actions if a.is_default), None)

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        if context.node.node_kind != "resource" or context.node.resource_type != "file":
            return ResourceActionResult(
                success=False,
                error_message="Invalid node type for File provider.",
            )

        # Resolve the file path using either context override or node service
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

        if action_id == "open_file":
            try:
                PlatformLauncher.open_path(resolved_path)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    message=f"Successfully opened file: {resolved_path}",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except LaunchError as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "edit_file":
            editor_cmd = os.environ.get("EDITOR") or os.environ.get("VISUAL")
            if not editor_cmd:
                return ResourceActionResult(
                    success=False,
                    error_message=(
                        "No editor configured. Please configure the EDITOR or VISUAL "
                        "environment variable (e.g. export EDITOR='nano')."
                    ),
                )

            # Split safely to avoid any shell interpolation or injection
            try:
                argv = shlex.split(editor_cmd)
                if not argv:
                    raise ValueError("Empty editor command.")
            except ValueError as e:
                return ResourceActionResult(
                    success=False,
                    error_message=f"Failed to parse editor command: {e}",
                )

            try:
                PlatformLauncher.launch_editor(argv, resolved_path)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    message=f"Successfully launched editor: {resolved_path}",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except LaunchError as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "copy_path":
            return ResourceActionResult(
                success=True,
                exit_app=False,
                output_value=f"Path: {resolved_path}",
                message=f"Copied path: {resolved_path}",
                target=ResourceActionResultTarget.DETAILS,
            )

        elif action_id == "view_details":
            try:
                path_obj = Path(resolved_path)
                size = path_obj.stat().st_size
                size_str = f"{size} bytes"
                suffix_str = path_obj.suffix or "None"
            except OSError as e:
                size_str = f"Error reading size ({e})"
                suffix_str = "Unknown"

            metadata = (
                f"Name: {context.node.name}\n"
                f"Path: {resolved_path}\n"
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
