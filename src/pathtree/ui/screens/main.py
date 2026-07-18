"""Main interface screen for PathTree."""

import uuid
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, Tree

from pathtree.services.node_service import NodeService, NodeServiceError
from pathtree.ui.widgets.details import NodeDetailsPanel
from pathtree.ui.widgets.search import SearchInput
from pathtree.ui.widgets.tree import NodeTreeView


class MainScreen(Screen[None]):
    """The main user interface screen for PathTree."""

    CSS = """
    SearchInput {
        dock: top;
        margin-bottom: 1;
    }
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
        self._last_query: str = ""
        self._last_selected_node_id: uuid.UUID | None = None

    def compose(self) -> ComposeResult:
        """Compose the screen widgets."""
        yield Header()
        yield SearchInput(id="search-input")
        with Horizontal():
            yield NodeTreeView(self.node_service, id="tree-view")
            yield NodeDetailsPanel(id="details-panel")
        yield Footer()

    def on_mount(self) -> None:
        """Focus the tree view on startup and show initial selection."""
        tree = self.query_one("#tree-view", NodeTreeView)
        tree.focus()
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)
        if tree.load_error:
            details_panel.update_error(tree.load_error)
        else:
            self._update_details_and_selection()

    def _update_details_and_selection(self) -> None:
        """Utility to safely update details panel based on selected tree cursor."""
        tree = self.query_one("#tree-view", NodeTreeView)
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)

        if tree.load_error:
            details_panel.update_error(tree.load_error)
            return

        # Check if DB is empty
        root_nodes = self.node_service.load_root_nodes()
        if not root_nodes:
            details_panel.update_node(None, empty_message="No nodes yet")
            return

        cursor_node = tree.cursor_node
        if cursor_node is None or cursor_node.data is None:
            # We are filtered and no matches
            details_panel.update_node(None, empty_message="No matching nodes")
            return

        # Load node details
        node = self.node_service.get_node(cursor_node.data)
        details_panel.update_node(node)
        self._last_selected_node_id = cursor_node.data

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[uuid.UUID]) -> None:
        """Update the details panel whenever the highlighted node changes."""
        self._update_details_and_selection()

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
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)
        if not self.output_path:
            details_panel.update_error(
                "No output file specified. Activation requires the --output option."
            )
            return

        try:
            resolved_path = self.node_service.resolve_node_path(node_id)
            with open(self.output_path, "w", encoding="utf-8") as f:
                f.write(str(resolved_path.absolute()))
            self.app.exit(return_code=0)
        except (NodeServiceError, OSError) as e:
            details_panel.update_error(str(e))

    # --- Search Input Interactions & Event Handlers ---

    def on_node_tree_view_focus_search(self, event: NodeTreeView.FocusSearch) -> None:
        """Focus SearchInput when '/' or 's' is pressed in the tree."""
        search_input = self.query_one("#search-input", SearchInput)
        search_input.focus()

    def on_input_changed(self, event: SearchInput.Changed) -> None:
        """Perform real-time filtering as search query changes."""
        query = event.value
        # Avoid redundant work if value is unchanged
        if query == self._last_query:
            return
        self._last_query = query

        tree = self.query_one("#tree-view", NodeTreeView)
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)

        # Get search results from service
        try:
            filtered_nodes = self.node_service.search_nodes(query=query)
        except NodeServiceError as e:
            details_panel.update_error(str(e))
            return

        # Load filtered tree, trying to preserve selection if possible
        # Expand all children when query is active
        expand_all = bool(query.strip())
        tree.load_tree(
            filtered_nodes,
            selected_node_id=self._last_selected_node_id,
            expand_all=expand_all,
        )

        # If no nodes are returned under a query (search returns empty)
        if not filtered_nodes and query.strip():
            # Clear cursor node highlight since there are no visible tree nodes
            tree.move_cursor(None)
            details_panel.update_node(None, empty_message="No matching nodes")
        else:
            self._update_details_and_selection()

    def on_search_input_escape_pressed(self, event: SearchInput.EscapePressed) -> None:
        """Clear query, restore full tree, and return focus to NodeTreeView."""
        search_input = self.query_one("#search-input", SearchInput)
        search_input.value = ""
        self._last_query = ""

        tree = self.query_one("#tree-view", NodeTreeView)
        try:
            full_nodes = self.node_service.get_validated_tree()
            tree.load_tree(full_nodes, selected_node_id=self._last_selected_node_id)
        except NodeServiceError as e:
            details_panel = self.query_one("#details-panel", NodeDetailsPanel)
            details_panel.update_error(str(e))

        tree.focus()
        self._update_details_and_selection()

    def on_search_input_down_pressed(self, event: SearchInput.DownPressed) -> None:
        """Move focus to NodeTreeView."""
        tree = self.query_one("#tree-view", NodeTreeView)
        tree.focus()

    def on_search_input_enter_pressed(self, event: SearchInput.EnterPressed) -> None:
        """Move focus to NodeTreeView on Enter (without immediate activation)."""
        tree = self.query_one("#tree-view", NodeTreeView)
        tree.focus()
