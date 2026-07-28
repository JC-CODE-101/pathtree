"""Action provider for multi launcher resources."""

from pathtree.actions.base import (
    ResourceAction,
    ResourceActionContext,
    ResourceActionProvider,
    ResourceActionResult,
    ResourceActionResultTarget,
)
from pathtree.services.multi_launcher_service import (
    MultiLauncherService,
    MultiLauncherServiceError,
)


class MultiLauncherActionProvider(ResourceActionProvider):
    """Action provider for 'multi_launcher' resource types."""

    def __init__(
        self, node_service, multi_launcher_service: MultiLauncherService
    ) -> None:
        """Initialize the MultiLauncherActionProvider."""
        self._node_service = node_service
        self._multi_launcher_service = multi_launcher_service

    @property
    def resource_type(self) -> str:
        """The supported resource type."""
        return "multi_launcher"

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for multi launcher resources."""
        return [
            ResourceAction(
                id="run_launcher",
                label="Run Multi Launcher",
                description="Execute all enabled profiles sequentially",
                is_default=True,
            ),
            ResourceAction(
                id="edit_launcher",
                label="Edit Multi Launcher",
                description="Manage profiles list, delay, and reorder items",
            ),
            ResourceAction(
                id="duplicate_launcher",
                label="Duplicate Multi Launcher",
                description="Duplicate this launcher and its items",
            ),
            ResourceAction(
                id="view_details",
                label="View Details",
                description="Show multi launcher execution details",
            ),
            ResourceAction(
                id="delete_launcher",
                label="Delete Multi Launcher",
                description="Delete this multi launcher and its node",
            ),
        ]

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for multi launcher resources."""
        actions = self.get_available_actions(context)
        return next((a for a in actions if a.is_default), None)

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        if (
            context.node.node_kind != "resource"
            or context.node.resource_type != "multi_launcher"
        ):
            return ResourceActionResult(
                success=False,
                error_message="Invalid node type for Multi Launcher provider.",
            )

        try:
            launcher = self._multi_launcher_service.get_launcher_for_node(
                context.node.id
            )
        except MultiLauncherServiceError as e:
            return ResourceActionResult(
                success=False,
                error_message=str(e),
            )

        if action_id == "run_launcher":
            try:
                self._multi_launcher_service.execute_launcher(launcher.id)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    message=f"Executed Multi Launcher: {context.node.name}",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "edit_launcher":
            # Handled by UI modal dialogs
            return ResourceActionResult(
                success=True,
                exit_app=False,
                target=ResourceActionResultTarget.NONE,
            )

        elif action_id == "duplicate_launcher":
            try:
                self._multi_launcher_service.duplicate_launcher(launcher.id)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    message=f"Duplicated Multi Launcher: {context.node.name}",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "delete_launcher":
            try:
                self._multi_launcher_service.delete_launcher(launcher.id)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    message=f"Deleted Multi Launcher: {context.node.name}",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "view_details":
            # Build details view string listing all items
            items = self._multi_launcher_service.repository.list_items_for_launcher(
                launcher.id
            )
            items_lines = []
            for item in items:
                try:
                    profile = (
                        self._multi_launcher_service.launch_profile_service.get_profile(
                            item.launch_profile_id
                        )
                    )
                    profile_node = self._node_service.get_node(profile.profile_node_id)
                    p_name = profile_node.name if profile_node else "Unknown Profile"
                except Exception:
                    p_name = "Unknown Profile"

                status_str = "Enabled" if item.enabled else "Disabled"
                item_lbl = (
                    f"  {item.position}. {p_name} "
                    f"({status_str}, delay: {item.delay_ms}ms)"
                )
                items_lines.append(item_lbl)

            if items_lines:
                items_str = "\n".join(items_lines)
            else:
                items_str = "  No profiles added."

            metadata = (
                f"Name: {context.node.name}\n"
                f"Resource Type: multi_launcher\n"
                f"Description: {context.node.description or 'None'}\n"
                f"Launch Profiles:\n{items_str}"
            )

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
