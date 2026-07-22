"""Registry for resource action providers."""

from pathtree.actions.base import ResourceActionProvider


class ResourceActionRegistry:
    """Registry that resolves the correct provider for a Node/resource_type."""

    def __init__(self) -> None:
        """Initialize the ResourceActionRegistry."""
        self._providers: dict[tuple[str, str | None], ResourceActionProvider] = {}

    def register(
        self,
        node_kind: str,
        resource_type: str | None,
        provider: ResourceActionProvider,
    ) -> None:
        """Registers a provider for a specific node kind and resource type."""
        self._providers[(node_kind, resource_type)] = provider

    def get_provider(
        self, node_kind: str, resource_type: str | None
    ) -> ResourceActionProvider | None:
        """Resolves the correct provider for a node kind and resource type.

        Returns None for Workspace and Folder nodes, as they are not treated
        as executable resources.
        """
        if node_kind in ("workspace", "folder"):
            return None
        return self._providers.get((node_kind, resource_type))
