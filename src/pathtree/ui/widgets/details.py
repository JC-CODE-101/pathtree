"""Widget displaying detailed information about the highlighted node."""

from textual.widgets import Static

from pathtree.models.node import Node


class NodeDetailsPanel(Static):
    """Widget displaying detailed information about the highlighted node."""

    def on_mount(self) -> None:
        """Set initial status message on mount."""
        self.update_node(None)

    def update_node(self, node: Node | None) -> None:
        """Update the panel with details of the provided node.

        Args:
            node: The Node object to display, or None if no node is selected.
        """
        if node is None:
            self.update("No node selected.")
            return

        name = node.name
        node_type = node.node_type
        path = node.path if node.path else "N/A"
        description = node.description if node.description else "N/A"

        content = (
            f"[bold]Name:[/bold] {name}\n"
            f"[bold]Type:[/bold] {node_type}\n"
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
