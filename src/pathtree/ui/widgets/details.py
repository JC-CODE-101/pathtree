"""Widget displaying detailed information about the highlighted node."""

from textual.widgets import Static

from pathtree.models.node import Node


class NodeDetailsPanel(Static):
    """Widget displaying detailed information about the highlighted node."""

    def __init__(self, **kwargs) -> None:
        """Initialize the NodeDetailsPanel with default text."""
        super().__init__("No node selected.", **kwargs)

    def update_node(
        self, node: Node | None, empty_message: str = "No node selected."
    ) -> None:
        """Update the panel with details of the provided node.

        Args:
            node: The Node object to display, or None if no node is selected.
            empty_message: Custom message to display if node is None.
        """
        if node is None:
            self.update(empty_message)
            return

        name = node.name
        node_type = node.resource_type if node.resource_type else node.node_kind
        path = node.path if node.path else "N/A"
        description = node.description if node.description else "N/A"

        from pathtree.utils.icons import icon_registry

        icon = icon_registry.get_icon(node)

        content = (
            f"[bold]Name:[/bold] {name}\n"
            f"[bold]Type:[/bold] {node_type}\n"
            f"[bold]Icon:[/bold] {icon}\n"
            f"[bold]Path:[/bold] {path}\n"
            f"[bold]Description:[/bold] {description}"
        )
        self.update(content)

    def update_error(self, message: str) -> None:
        """Display an error message inside the panel.

        Args:
            message: The error message to display.
        """
        self.update(f"[bold red]Error:[/bold red] {message}")
