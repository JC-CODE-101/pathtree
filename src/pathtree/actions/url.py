"""Action provider for URL resources."""

from urllib.parse import urlparse

from pathtree.actions.base import (
    ResourceAction,
    ResourceActionContext,
    ResourceActionProvider,
    ResourceActionResult,
    ResourceActionResultTarget,
)
from pathtree.services.node_service import NodeService
from pathtree.utils.launcher import LaunchError, PlatformLauncher


class UrlActionProvider(ResourceActionProvider):
    """Action provider for 'url' resource types."""

    def __init__(self, node_service: NodeService) -> None:
        """Initialize the UrlActionProvider with a NodeService."""
        self._node_service = node_service

    @property
    def resource_type(self) -> str:
        """The supported resource type."""
        return "url"

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for URL resources."""
        return [
            ResourceAction(
                id="open_url",
                label="Open URL",
                description="Open this URL in the system default browser",
                is_default=True,
            ),
            ResourceAction(
                id="copy_url",
                label="Copy URL",
                description="Copy URL to clipboard",
            ),
            ResourceAction(
                id="view_details",
                label="View Details",
                description="Show URL details",
            ),
        ]

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for URL resources."""
        actions = self.get_available_actions(context)
        return next((a for a in actions if a.is_default), None)

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        if context.node.node_kind != "resource" or context.node.resource_type != "url":
            return ResourceActionResult(
                success=False,
                error_message="Invalid node type for URL provider.",
            )

        url = context.node.path or ""

        if action_id == "open_url":
            try:
                PlatformLauncher.open_url(url)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    message=f"Successfully opened URL: {url}",
                    target=ResourceActionResultTarget.NOTIFICATION,
                )
            except LaunchError as e:
                return ResourceActionResult(
                    success=False,
                    error_message=str(e),
                )

        elif action_id == "copy_url":
            try:
                PlatformLauncher.copy_to_clipboard(url)
                return ResourceActionResult(
                    success=True,
                    exit_app=False,
                    output_value=f"URL: {url}",
                    message=f"Copied URL to clipboard: {url}",
                    target=ResourceActionResultTarget.DETAILS,
                )
            except Exception as e:
                return ResourceActionResult(
                    success=False,
                    error_message=f"Clipboard error: {e}",
                )

        elif action_id == "view_details":
            try:
                parsed = urlparse(url)
                scheme = parsed.scheme or "Unknown"
                domain = parsed.netloc or "Unknown"
                path = parsed.path or "None"
            except Exception:
                scheme = "Unknown"
                domain = "Unknown"
                path = "Unknown"

            metadata = (
                f"Name: {context.node.name}\n"
                f"URL: {url}\n"
                f"Scheme: {scheme}\n"
                f"Domain: {domain}\n"
                f"Path: {path}"
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
