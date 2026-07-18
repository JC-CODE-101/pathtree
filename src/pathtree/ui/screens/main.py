"""Main interface screen for PathTree."""

import uuid
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Tree

from pathtree.services.node_service import NodeService
from pathtree.ui.widgets.details import NodeDetailsPanel
from pathtree.ui.widgets.tree import NodeTreeView


class MainScreen(Screen[None]):
    """The main user interface screen for PathTree."""

    CSS = """
    Horizontal {
        height: 1fr;
    }
    #tree-view {
        width: 65%;
        border-right: solid $accent;
    }
    #details-panel {
        width: 35%;
        padding: 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "activate_selected", "Select", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self, node_service: NodeService, output_path: str | None = None
    ) -> None:
        """Initialize MainScreen with the node service and optional output path."""
        super().__init__(id="main-screen")
        self.node_service = node_service
        self.output_path = output_path

    def compose(self) -> ComposeResult:
        """Compose the screen widgets."""
        yield Header()
        with Horizontal():
            yield NodeTreeView(self.node_service, id="tree-view")
            yield NodeDetailsPanel(id="details-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the tree view on startup and show initial selection."""
        tree = self.query_one("#tree-view", NodeTreeView)
        tree.focus()
        if tree.cursor_node is not None and tree.cursor_node.data is not None:
            node = self.node_service.get_node(tree.cursor_node.data)
            self.query_one("#details-panel", NodeDetailsPanel).update_node(node)

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[uuid.UUID]) -> None:
        """Update the details panel whenever the highlighted node changes."""
        node_id = event.node.data
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)
        if node_id is None:
            details_panel.update_node(None)
            return

        node = self.node_service.get_node(node_id)
        details_panel.update_node(node)

    def on_tree_node_selected(self, event: Tree.NodeSelected[uuid.UUID]) -> None:
        """Handle node activation when Enter is pressed on a node."""
        node_id = event.node.data
        if node_id is None:
            return
        self.activate_node(node_id)

    def action_activate_selected(self) -> None:
        """Fallback action to activate the currently highlighted node."""
        tree = self.query_one("#tree-view", NodeTreeView)
        if tree.cursor_node is not None and tree.cursor_node.data is not None:
            self.activate_node(tree.cursor_node.data)

    def action_quit(self) -> None:
        """Quit the application safely with exit code 0."""
        self.app.exit(return_code=0)

    def activate_node(self, node_id: uuid.UUID) -> None:
        """Resolve node path and handle activation."""
        try:
            resolved_path = self.node_service.resolve_node_path(node_id)
            if self.output_path:
                with open(self.output_path, "w", encoding="utf-8") as f:
                    f.write(str(resolved_path.absolute()))
            self.app.exit(return_code=0)
        except Exception as e:
            details_panel = self.query_one("#details-panel", NodeDetailsPanel)
            details_panel.update_error(str(e))
