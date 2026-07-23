"""Action provider for script resources."""

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
from pathtree.utils.script_resolver import ScriptResolutionError, resolve_script_argv


class ScriptActionProvider(ResourceActionProvider):
    """Action provider for 'script' resource types."""

    def __init__(self, node_service: NodeService) -> None:
        """Initialize the ScriptActionProvider with a NodeService."""
        self._node_service = node_service

    @property
    def resource_type(self) -> str:
        """The supported resource type."""
        return "script"

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for script resources."""
        return [
            ResourceAction(
                id="run_script",
                label="Run Script",
                description="Execute this script safely",
                is_default=True,
            ),
            ResourceAction(
                id="edit_script",
                label="Edit Script",
                description="Open this script in your configured editor",
            ),
            ResourceAction(
                id="copy_path",
                label="Copy Path",
                description="Copy script path to details panel",
            ),
            ResourceAction(
                id="view_details",
                label="View Details",
                description="Show script metadata and execution details",
            ),
        ]

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for script resources."""
        actions = self.get_available_actions(context)
        return next((a for a in actions if a.is_default), None)

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        if (
            context.node.node_kind != "resource"
            or context.node.resource_type != "script"
        ):
            return ResourceActionResult(
                success=False,
                error_message="Invalid node type for Script provider.",
            )

        # Resolve the script path using either context override or node service
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

        if action_id == "run_script":
            try:
                argv = resolve_script_argv(path_obj)
            except ScriptResolutionError as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

            # Working directory for execution is the parent directory of the script
            cwd = path_obj.parent

            res = PlatformLauncher.launch_process(argv, cwd=cwd)
            if not res.success:
                return ResourceActionResult(
                    success=False,
                    error_message=res.error_message or "Process launch failed.",
                )

            return ResourceActionResult(
                success=True,
                exit_app=False,
                message=f"Successfully executed script: {path_obj.name}",
                target=ResourceActionResultTarget.NOTIFICATION,
            )

        elif action_id == "edit_script":
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
            exists = path_obj.exists()
            is_executable = os.access(path_obj, os.X_OK) if exists else False
            working_dir = str(path_obj.parent.absolute()) if exists else "Unknown"

            # Determine interpreter/execution mode without running the script
            try:
                argv = resolve_script_argv(path_obj)
                detected_interpreter = argv[0] if argv else "Direct Execution"
                if len(argv) == 1 and argv[0] == str(path_obj):
                    detected_interpreter = "Direct Execution"
            except ScriptResolutionError as e:
                detected_interpreter = f"Error detecting interpreter ({e})"

            metadata = (
                f"Name: {context.node.name}\n"
                f"Resource Type: script\n"
                f"Full Script Path: {resolved_path}\n"
                f"Detected Interpreter: {detected_interpreter}\n"
                f"Working Directory: {working_dir}\n"
                f"Path Exists: {'Yes' if exists else 'No'}\n"
                f"File Is Executable: {'Yes' if is_executable else 'No'}"
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
