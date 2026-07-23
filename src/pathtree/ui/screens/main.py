"""Main interface screen for PathTree."""

import uuid
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, Tree

from pathtree.actions import (
    DirectoryActionProvider,
    ResourceActionContext,
    ResourceActionRegistry,
)
from pathtree.actions.base import ResourceActionResultTarget
from pathtree.services.node_service import NodeService, NodeServiceError
from pathtree.ui.dialogs.action_menu import ActionMenuResult, ResourceActionMenu
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.dialogs.confirm_delete import ConfirmDeleteDialog, DeleteResult
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.dialogs.move_node import MoveNodeDialog
from pathtree.ui.state import TreeState, TreeStateStore
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
        self,
        node_service: NodeService,
        output_path: str | None = None,
        state_store: TreeStateStore | None = None,
    ) -> None:
        """Initialize MainScreen with service, output path, and state store."""
        super().__init__(id="main-screen")
        self.node_service = node_service
        self.output_path = output_path
        self.state_store = state_store or TreeStateStore()
        self._last_query: str = ""
        self._last_selected_node_id: uuid.UUID | None = None
        self._pre_search_selected_node_id: uuid.UUID | None = None
        self._pre_search_expanded_node_ids: set[uuid.UUID] | None = None
        self._db_is_empty: bool = False
        self._current_tree_state: TreeState = TreeState()

        # Initialize Action Registry and Register Providers
        self.action_registry = ResourceActionRegistry()
        self.action_registry.register(
            "resource", "directory", DirectoryActionProvider(self.node_service)
        )
        from pathtree.actions.file import FileActionProvider

        self.action_registry.register(
            "resource", "file", FileActionProvider(self.node_service)
        )
        from pathtree.actions.script import ScriptActionProvider

        self.action_registry.register(
            "resource", "script", ScriptActionProvider(self.node_service)
        )

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

        # Cache whether the database is empty on mount to avoid redundant queries
        try:
            root_nodes = self.node_service.load_root_nodes()
            self._db_is_empty = not root_nodes
        except NodeServiceError as e:
            self._db_is_empty = False
            details_panel.update_error(str(e))
            return

        if tree.load_error:
            details_panel.update_error(tree.load_error)
            return

        # Load and restore persistent UI state
        self._current_tree_state = self.state_store.load()
        if (
            self._current_tree_state.expanded_node_ids
            or self._current_tree_state.selected_node_id is not None
        ):
            try:
                tree_nodes = self.node_service.get_validated_tree()

                # Get existing node IDs to prevent restoring deleted/moved nodes
                existing_ids = set()

                def collect_ids(nodes):
                    for n in nodes:
                        existing_ids.add(n.node.id)
                        collect_ids(n.children)

                collect_ids(tree_nodes)

                restored_sel_id = self._current_tree_state.selected_node_id
                if restored_sel_id is not None and restored_sel_id not in existing_ids:
                    restored_sel_id = None

                restored_exp_ids = {
                    eid
                    for eid in self._current_tree_state.expanded_node_ids
                    if eid in existing_ids
                }

                tree.load_tree(
                    tree_nodes,
                    selected_node_id=restored_sel_id,
                    expanded_node_ids=restored_exp_ids,
                )
            except NodeServiceError as e:
                details_panel.update_error(str(e))
                return

        self.call_after_refresh(self._update_details_and_selection)

    def _update_details_and_selection(self) -> None:
        """Utility to safely update details panel based on selected tree cursor."""
        tree = self.query_one("#tree-view", NodeTreeView)
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)

        if tree.load_error:
            details_panel.update_error(tree.load_error)
            return

        # Check if DB is empty from cached state
        if self._db_is_empty:
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
        if tree.has_focus or self._last_selected_node_id is None:
            self._last_selected_node_id = cursor_node.data

        # Keep current state available for persistence
        self._update_persistent_state()

    def on_unmount(self) -> None:
        """Save the tree state on screen unmount/dismissal."""
        self.save_state()

    def _update_persistent_state(self) -> None:
        """Update the state object with latest user expansion and selection."""
        try:
            tree = self.query_one("#tree-view", NodeTreeView)
        except NoMatches:
            return

        if tree.load_error:
            return

        # If a search query is active, use the pre-search expansion/selection states so
        # temporary search-expansions do not corrupt the persistent tree state.
        if self._last_query.strip():
            expanded_ids = self._pre_search_expanded_node_ids or set()
            selected_id = (
                self._pre_search_selected_node_id or self._last_selected_node_id
            )
        else:
            expanded_ids = tree.get_expanded_node_ids()
            selected_id = self._last_selected_node_id

        self._current_tree_state.expanded_node_ids = set(expanded_ids)
        self._current_tree_state.selected_node_id = selected_id

    def save_state(self) -> None:
        """Save the current tree state to the persistence store."""
        self._update_persistent_state()
        self.state_store.save(self._current_tree_state)

    def on_tree_node_expanded(self, event: Tree.NodeExpanded[uuid.UUID]) -> None:
        """Handle tree node expansion and update persistence state."""
        self._update_persistent_state()

    def on_tree_node_collapsed(self, event: Tree.NodeCollapsed[uuid.UUID]) -> None:
        """Handle tree node collapsing and update persistence state."""
        self._update_persistent_state()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[uuid.UUID]) -> None:
        """Update the details panel whenever the highlighted node changes."""
        self._update_details_and_selection()

    def on_node_tree_view_activate_node(self, event: NodeTreeView.ActivateNode) -> None:
        """Handle the custom ActivateNode message from the tree view."""
        self.activate_node(event.node_id)

    def action_activate_selected(self) -> None:
        """Fallback action to activate the currently highlighted node."""
        tree = self.query_one("#tree-view", NodeTreeView)
        if not tree.has_focus:
            return
        if tree.cursor_node is not None and tree.cursor_node.data is not None:
            self.post_message(NodeTreeView.ActivateNode(tree.cursor_node.data))

    def action_quit(self) -> None:
        """Quit the application safely with exit code 0."""
        self.save_state()
        self.app.exit(return_code=0)

    def on_node_tree_view_open_action_menu(
        self, event: NodeTreeView.OpenActionMenu
    ) -> None:
        """Handle 'o' / 'O' key in tree to open Action Menu."""
        tree = self.query_one("#tree-view", NodeTreeView)
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)

        if tree.cursor_node is None or tree.cursor_node.data is None:
            details_panel.update_error("No node selected.")
            return

        node_id = tree.cursor_node.data
        node = self.node_service.get_node(node_id)
        if node is None:
            details_panel.update_error("Node not found.")
            return

        # 1. Selected node must be a Resource
        if node.node_kind != "resource":
            details_panel.update_error(
                f"Action Menu is not available for {node.node_kind.capitalize()} nodes."
            )
            return

        # 2. Registry must resolve a provider
        provider = self.action_registry.get_provider(node.node_kind, node.resource_type)
        if not provider:
            res_type = node.resource_type or "None"
            msg = f"No action provider found for resource type '{res_type}'."
            details_panel.update_error(msg)
            return

        # 3. Provider must return at least one available action
        context = ResourceActionContext(
            node=node,
            output_path=self.output_path,
        )
        actions = provider.get_available_actions(context)
        if not actions:
            details_panel.update_error("No available actions for this resource.")
            return

        def handle_action_menu_finished(result: ActionMenuResult | None) -> None:
            tree.focus()
            if result is not None and result.action_id is not None:
                self.execute_action(result.action_id, provider, context)

        self.app.push_screen(
            ResourceActionMenu(actions, title=f"Actions for {node.name}"),
            callback=handle_action_menu_finished,
        )

    def execute_action(
        self,
        action_id: str,
        provider,
        context: ResourceActionContext,
    ) -> None:
        """Execute action and centrally handle results generically."""
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)

        # Verify disabled actions cannot execute
        actions = provider.get_available_actions(context)
        action_obj = next((a for a in actions if a.id == action_id), None)
        if action_obj is not None and not action_obj.is_enabled:
            details_panel.update_error(f"Action '{action_obj.label}' is disabled.")
            return

        result = provider.execute(action_id, context)
        if not result.success:
            err = result.error_message or "Action execution failed."
            details_panel.update_error(err)
            return

        if result.message:
            self.app.notify(result.message)

        # Render output_value according to the typed target
        if result.target == ResourceActionResultTarget.DETAILS:
            if result.output_value is not None:
                details_panel.update(result.output_value)
        elif result.target == ResourceActionResultTarget.NOTIFICATION:
            if result.output_value is not None:
                self.app.notify(result.output_value)

        if result.exit_app:
            self.save_state()
            self.app.exit(return_code=0)

    def activate_node(self, node_id: uuid.UUID) -> None:
        """Resolve node path and handle activation."""
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)

        node = self.node_service.get_node(node_id)
        if not node:
            details_panel.update_error(f"Node {node_id} does not exist.")
            return

        provider = self.action_registry.get_provider(node.node_kind, node.resource_type)
        if not provider:
            details_panel.update_error(
                "No default action is available for this node type."
            )
            return

        context = ResourceActionContext(
            node=node,
            output_path=self.output_path,
        )
        default_action = provider.get_default_action(context)
        if not default_action:
            details_panel.update_error(f"No default action defined for '{node.name}'.")
            return

        result = provider.execute(default_action.id, context)

        if not result.success:
            details_panel.update_error(result.error_message or "Action failed.")
            return

        if result.exit_app:
            self.save_state()
            self.app.exit(return_code=0)

    # --- Search Input Interactions & Event Handlers ---

    def refresh_tree(
        self,
        selected_node_id: uuid.UUID | None = None,
        fallback_node_id: uuid.UUID | None = None,
        expanded_node_ids: set[uuid.UUID] | None = None,
    ) -> None:
        """Refresh the visible tree.

        Preserves search filter and selects the appropriate node.
        """
        tree = self.query_one("#tree-view", NodeTreeView)
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)

        # Capture expanded node IDs before rebuilding if not explicitly supplied
        if expanded_node_ids is None:
            expanded_node_ids = tree.get_expanded_node_ids()
        else:
            expanded_node_ids = set(expanded_node_ids)

        # Update cached empty database status
        try:
            root_nodes = self.node_service.load_root_nodes()
            self._db_is_empty = not root_nodes
        except NodeServiceError as e:
            self._db_is_empty = False
            details_panel.update_error(str(e))
            return

        # Fetch filtered nodes using current query
        try:
            filtered_nodes = self.node_service.search_nodes(query=self._last_query)
        except NodeServiceError as e:
            details_panel.update_error(str(e))
            return

        is_now_non_empty = bool(self._last_query.strip())

        # Build list of visible IDs in the filtered tree
        visible_ids = []

        def gather_ids(t_nodes):
            for tn in t_nodes:
                visible_ids.append(tn.node.id)
                gather_ids(tn.children)

        gather_ids(filtered_nodes)

        # Selection fallback logic
        target_id = None
        if selected_node_id is not None and selected_node_id in visible_ids:
            target_id = selected_node_id
        elif fallback_node_id is not None and fallback_node_id in visible_ids:
            target_id = fallback_node_id
        elif visible_ids:
            target_id = visible_ids[0]

        # Keep track of selected ID
        self._last_selected_node_id = target_id

        # After Add or Move (or any select), ensure complete ancestor chain is expanded
        if target_id is not None:
            curr_id = target_id
            while curr_id is not None:
                curr_node = self.node_service.get_node(curr_id)
                if curr_node is None:
                    break
                if curr_node.parent_id is not None:
                    expanded_node_ids.add(curr_node.parent_id)
                curr_id = curr_node.parent_id

        # Reload tree in the widget
        tree.load_tree(
            filtered_nodes,
            selected_node_id=target_id,
            expand_all=is_now_non_empty,
            expanded_node_ids=expanded_node_ids,
        )

        if not filtered_nodes and is_now_non_empty:
            tree.move_cursor(None)

        self.call_after_refresh(self._update_details_and_selection)

    def on_node_tree_view_focus_search(self, event: NodeTreeView.FocusSearch) -> None:
        """Focus SearchInput when '/' or 's' is pressed in the tree."""
        search_input = self.query_one("#search-input", SearchInput)
        search_input.focus()

    def on_node_tree_view_add_node(self, event: NodeTreeView.AddNode) -> None:
        """Handle 'a' key in tree to open Add Node Dialog."""
        tree = self.query_one("#tree-view", NodeTreeView)

        # Capture expansion state before opening the dialog
        captured_expanded_node_ids = tree.get_expanded_node_ids()

        # Default parent behavior:
        # No selection -> Root
        # Workspace -> selected workspace
        # Folder -> selected folder
        # Directory resource -> parent of directory resource
        default_parent_id = None
        if tree.cursor_node is not None and tree.cursor_node.data is not None:
            node = self.node_service.get_node(tree.cursor_node.data)
            if node is not None:
                if node.node_kind in ("workspace", "folder"):
                    default_parent_id = node.id
                elif node.node_kind == "resource":
                    default_parent_id = node.parent_id

        def handle_add_finished(new_node_id: uuid.UUID | None) -> None:
            if new_node_id is not None:
                # Get the node to show success feedback
                new_node = self.node_service.get_node(new_node_id)
                if new_node is not None:
                    node_type_label = (
                        new_node.resource_type
                        if new_node.resource_type
                        else new_node.node_kind
                    )
                    self.app.notify(f'Created {node_type_label} "{new_node.name}"')
                self.refresh_tree(
                    selected_node_id=new_node_id,
                    expanded_node_ids=captured_expanded_node_ids,
                )
            tree.focus()

        self.app.push_screen(
            AddNodeDialog(self.node_service, default_parent_id=default_parent_id),
            callback=handle_add_finished,
        )

    def on_node_tree_view_edit_node(self, event: NodeTreeView.EditNode) -> None:
        """Handle 'e' key in tree to open Edit Node Dialog."""
        tree = self.query_one("#tree-view", NodeTreeView)
        if tree.cursor_node is None or tree.cursor_node.data is None:
            return

        # Capture expansion state before opening the dialog
        captured_expanded_node_ids = tree.get_expanded_node_ids()
        node_id = tree.cursor_node.data

        def handle_edit_finished(success: bool) -> None:
            if success:
                node = self.node_service.get_node(node_id)
                if node is not None:
                    self.app.notify(f'Updated "{node.name}"')
                self.refresh_tree(
                    selected_node_id=node_id,
                    expanded_node_ids=captured_expanded_node_ids,
                )
            tree.focus()

        self.app.push_screen(
            EditNodeDialog(self.node_service, node_id),
            callback=handle_edit_finished,
        )

    def on_node_tree_view_move_node(self, event: NodeTreeView.MoveNode) -> None:
        """Handle 'm' key in tree to open Move Node Dialog."""
        tree = self.query_one("#tree-view", NodeTreeView)
        if tree.cursor_node is None or tree.cursor_node.data is None:
            return

        # Capture expansion state before opening the dialog
        captured_expanded_node_ids = tree.get_expanded_node_ids()
        node_id = tree.cursor_node.data

        def handle_move_finished(success: bool) -> None:
            if success:
                node = self.node_service.get_node(node_id)
                if node is not None:
                    self.app.notify(f'Moved "{node.name}"')
                self.refresh_tree(
                    selected_node_id=node_id,
                    expanded_node_ids=captured_expanded_node_ids,
                )
            tree.focus()

        self.app.push_screen(
            MoveNodeDialog(self.node_service, node_id),
            callback=handle_move_finished,
        )

    def on_node_tree_view_delete_node(self, event: NodeTreeView.DeleteNode) -> None:
        """Handle 'd' or 'delete' key in tree to open Confirm Delete Dialog."""
        tree = self.query_one("#tree-view", NodeTreeView)
        if tree.cursor_node is None or tree.cursor_node.data is None:
            return

        # Capture expansion state before opening the dialog
        captured_expanded_node_ids = tree.get_expanded_node_ids()

        node_id = tree.cursor_node.data
        node = self.node_service.get_node(node_id)
        if node is None:
            return

        # Determine fallbacks: next sibling, else previous sibling, else parent,
        # else None (first visible root will be handled by refresh_tree).
        # To find siblings or parent, let's look at cursor_node in Textual tree
        fallback_node_id = None
        cursor_node = tree.cursor_node
        parent_node = cursor_node.parent
        if parent_node is not None:
            siblings = parent_node.children
            try:
                idx = siblings.index(cursor_node)
                if idx + 1 < len(siblings):
                    fallback_node_id = siblings[idx + 1].data
                elif idx - 1 >= 0:
                    fallback_node_id = siblings[idx - 1].data
                elif parent_node != tree.root:
                    fallback_node_id = parent_node.data
            except ValueError:
                pass

        def handle_delete_finished(result: DeleteResult | None) -> None:
            if result is not None and result.deleted:
                desc_count = result.descendant_count
                if desc_count > 0:
                    self.app.notify(
                        f'Deleted "{node.name}" and {desc_count} descendants'
                    )
                else:
                    self.app.notify(f'Deleted "{node.name}"')

                # Filter out the deleted node from captured expanded IDs
                remaining_expanded_ids = captured_expanded_node_ids - {node_id}
                self.refresh_tree(
                    fallback_node_id=fallback_node_id,
                    expanded_node_ids=remaining_expanded_ids,
                )
            tree.focus()

        self.app.push_screen(
            ConfirmDeleteDialog(self.node_service, node_id),
            callback=handle_delete_finished,
        )

    def on_input_changed(self, event: SearchInput.Changed) -> None:
        """Perform real-time filtering as search query changes."""
        query = event.value
        # Avoid redundant work if value is unchanged
        if query == self._last_query:
            return
        self._last_query = query

        tree = self.query_one("#tree-view", NodeTreeView)
        details_panel = self.query_one("#details-panel", NodeDetailsPanel)

        is_now_non_empty = bool(query.strip())

        # Capture pre-search selection and expansion state if transitioning
        # from empty to non-empty
        if is_now_non_empty and self._pre_search_selected_node_id is None:
            self._pre_search_selected_node_id = self._last_selected_node_id
            self._pre_search_expanded_node_ids = tree.get_expanded_node_ids()

        # Determine which expansion state to apply
        if not is_now_non_empty and self._pre_search_expanded_node_ids is not None:
            expanded_node_ids = self._pre_search_expanded_node_ids
            self._pre_search_expanded_node_ids = None
        else:
            expanded_node_ids = tree.get_expanded_node_ids()

        # Get search results from service
        try:
            filtered_nodes = self.node_service.search_nodes(query=query)
        except NodeServiceError as e:
            details_panel.update_error(str(e))
            return

        # Determine which node ID we want to restore/select
        restore_id = self._last_selected_node_id
        if not is_now_non_empty and self._pre_search_selected_node_id is not None:
            restore_id = self._pre_search_selected_node_id
            self._pre_search_selected_node_id = None

        # Load filtered tree, trying to preserve selection if possible
        # Expand all children when query is active
        tree.load_tree(
            filtered_nodes,
            selected_node_id=restore_id,
            expand_all=is_now_non_empty,
            expanded_node_ids=expanded_node_ids,
        )

        # If no nodes are returned under a query (search returns empty)
        if not filtered_nodes and query.strip():
            # Clear cursor node highlight since there are no visible tree nodes
            tree.move_cursor(None)

        self.call_after_refresh(self._update_details_and_selection)

    def on_search_input_escape_pressed(self, event: SearchInput.EscapePressed) -> None:
        """Clear query, restore full tree, and return focus to NodeTreeView."""
        search_input = self.query_one("#search-input", SearchInput)
        search_input.value = ""
        tree = self.query_one("#tree-view", NodeTreeView)
        tree.focus()

    def on_search_input_down_pressed(self, event: SearchInput.DownPressed) -> None:
        """Move focus to NodeTreeView."""
        tree = self.query_one("#tree-view", NodeTreeView)
        tree.focus()

    def on_search_input_enter_pressed(self, event: SearchInput.EnterPressed) -> None:
        """Move focus to NodeTreeView on Enter (without immediate activation)."""
        tree = self.query_one("#tree-view", NodeTreeView)
        tree.focus()
