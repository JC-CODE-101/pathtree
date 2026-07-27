"""Action provider for launch profile resources."""

from pathtree.actions.base import (
    ResourceAction,
    ResourceActionContext,
    ResourceActionProvider,
    ResourceActionResult,
    ResourceActionResultTarget,
)
from pathtree.services.launch_profile_service import (
    LaunchProfileService,
    LaunchProfileServiceError,
)


class LaunchProfileActionProvider(ResourceActionProvider):
    """Action provider for 'launch_profile' resource types."""

    def __init__(
        self, node_service, launch_profile_service: LaunchProfileService
    ) -> None:
        """Initialize the LaunchProfileActionProvider."""
        self._node_service = node_service
        self._launch_profile_service = launch_profile_service

    @property
    def resource_type(self) -> str:
        """The supported resource type."""
        return "launch_profile"

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for launch profile resources."""
        # Find if the profile is active/detached
        try:
            profile = self._launch_profile_service.get_profile_for_node(context.node.id)
            is_active = profile.status == "active"
        except Exception:
            is_active = True

        return [
            ResourceAction(
                id="run_profile",
                label="Run Profile",
                description="Execute this launch profile safely",
                is_default=True,
                is_enabled=is_active,
            ),
            ResourceAction(
                id="edit_profile",
                label="Edit Profile",
                description="Edit profile name, arguments, and settings",
            ),
            ResourceAction(
                id="reconnect_target",
                label="Reconnect Target",
                description="Reconnect profile to a compatible target",
            ),
            ResourceAction(
                id="view_details",
                label="View Details",
                description="Show launch profile execution details",
            ),
            ResourceAction(
                id="delete_profile",
                label="Delete Profile",
                description="Delete this launch profile and its node representation",
            ),
        ]

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for launch profile resources."""
        actions = self.get_available_actions(context)
        return next((a for a in actions if a.is_default), None)

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        if (
            context.node.node_kind != "resource"
            or context.node.resource_type != "launch_profile"
        ):
            return ResourceActionResult(
                success=False,
                error_message="Invalid node type for Launch Profile provider.",
            )

        try:
            profile = self._launch_profile_service.get_profile_for_node(context.node.id)
        except LaunchProfileServiceError as e:
            return ResourceActionResult(
                success=False,
                error_message=str(e),
            )

        if action_id == "run_profile":
            try:
                self._launch_profile_service.execute_profile(profile.id)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    message=f"Launched profile: {context.node.name}",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except LaunchProfileServiceError as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "edit_profile":
            # Handled by UI modal dialogs
            return ResourceActionResult(
                success=True,
                exit_app=False,
                target=ResourceActionResultTarget.NONE,
            )

        elif action_id == "reconnect_target":
            # Handled by UI modal dialogs
            return ResourceActionResult(
                success=True,
                exit_app=False,
                target=ResourceActionResultTarget.NONE,
            )

        elif action_id == "delete_profile":
            # Handled by UI modal dialogs
            return ResourceActionResult(
                success=True,
                exit_app=False,
                target=ResourceActionResultTarget.NONE,
            )

        elif action_id == "view_details":
            # Build details view string
            target_str = "None"
            if profile.target_node_id:
                t_node = self._node_service.get_node(profile.target_node_id)
                if t_node:
                    target_str = f"{t_node.name} (Type: {profile.target_resource_type})"
                    try:
                        resolved_path = self._node_service.resolve_node_path(t_node.id)
                        target_str += f"\nPath: {resolved_path}"
                    except Exception:
                        pass
            elif profile.status == "detached":
                target_str = (
                    f"DETACHED (Incompatible/Deleted)\n"
                    f"Previous Target: {profile.previous_target_name}\n"
                    f"Previous Path: {profile.previous_target_path}"
                )

            wd_str = "None (Preserves target default)"
            if profile.working_directory_node_id:
                wd_node = self._node_service.get_node(profile.working_directory_node_id)
                if wd_node:
                    wd_str = wd_node.name
                    try:
                        resolved_wd = self._node_service.resolve_node_path(wd_node.id)
                        wd_str += f" ({resolved_wd})"
                    except Exception:
                        pass

            args_list = profile.argv
            args_str = " ".join(args_list) if args_list else "None"

            metadata = (
                f"Name: {context.node.name}\n"
                f"Resource Type: launch_profile\n"
                f"Status: {profile.status.upper()}\n"
                f"Target Node: {target_str}\n"
                f"Arguments: {args_str}\n"
                f"Working Directory: {wd_str}\n"
                f"Terminal Mode: {profile.terminal_mode}"
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
