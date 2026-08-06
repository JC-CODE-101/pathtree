"""Main interface screen for PathTree."""

import uuid
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Header, Static, Tree

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
        height: 3;
        margin-bottom: 0;
    }
    Horizontal {
        height: 1fr;
    }
    #tree-view {
        width: 65%;
        min-width: 65%;
        max-width: 65%;
        border-right: solid $accent;
    }
    #details-panel {
        width: 35%;
        min-width: 35%;
        max-width: 35%;
        overflow-x: hidden;
        padding: 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("enter", "activate_selected", "Select", show=True),
        Binding("q", "quit", "Quit", show=True),
        Binding("escape", "leave_focus", "Back", show=False),
        Binding("backspace", "leave_focus", "Back", show=False),
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
        self._focused_group_id: uuid.UUID | None = None

        # Initialize Pin Service
        if (
            hasattr(self.node_service, "repository")
            and self.node_service.repository is not None
        ):
            from pathtree.database.repository import PinRepository
            from pathtree.services.pin_service import PinService

            pin_repo = PinRepository(self.node_service.repository.session)
            self.pin_service = PinService(self.node_service.repository, pin_repo)
        else:
            self.pin_service = None

        # Initialize Launch Profile Service
        if (
            hasattr(self.node_service, "repository")
            and self.node_service.repository is not None
        ):
            from pathtree.database.repository import LaunchProfileRepository
            from pathtree.services.launch_profile_service import LaunchProfileService

            lp_repo = LaunchProfileRepository(self.node_service.repository.session)
            self.launch_profile_service = LaunchProfileService(
                self.node_service, lp_repo
            )
        else:
            self.launch_profile_service = None

        # Initialize Multi Launcher Service
        if (
            hasattr(self.node_service, "repository")
            and self.node_service.repository is not None
            and self.launch_profile_service is not None
        ):
            from pathtree.database.repository import MultiLauncherRepository
            from pathtree.services.multi_launcher_service import MultiLauncherService

            ml_repo = MultiLauncherRepository(self.node_service.repository.session)
            self.multi_launcher_service = MultiLauncherService(
                self.node_service, self.launch_profile_service, ml_repo
            )
        else:
            self.multi_launcher_service = None

        # Initialize Workspace View Settings Service
        if (
            hasattr(self.node_service, "repository")
            and self.node_service.repository is not None
        ):
            session = getattr(self.node_service.repository, "session", None)
            if session is not None:
                from pathtree.database.repository import WorkspaceViewSettingsRepository
                from pathtree.services.workspace_view_settings_service import (
                    WorkspaceViewSettingsService,
                )

                wvs_repo = WorkspaceViewSettingsRepository(session)
                self.view_settings_service = WorkspaceViewSettingsService(wvs_repo)
            else:
                self.view_settings_service = None
        else:
            self.view_settings_service = None

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
        from pathtree.actions.executable import ExecutableActionProvider

        self.action_registry.register(
            "resource", "executable", ExecutableActionProvider(self.node_service)
        )
        from pathtree.actions.url import UrlActionProvider

        self.action_registry.register(
            "resource", "url", UrlActionProvider(self.node_service)
        )

        if self.launch_profile_service:
            from pathtree.actions.launch_profile import LaunchProfileActionProvider

            self.action_registry.register(
                "resource",
                "launch_profile",
                LaunchProfileActionProvider(
                    self.node_service, self.launch_profile_service
                ),
            )

        if self.multi_launcher_service:
            from pathtree.actions.multi_launcher import MultiLauncherActionProvider

            self.action_registry.register(
                "resource",
                "multi_launcher",
                MultiLauncherActionProvider(
                    self.node_service, self.multi_launcher_service
                ),
            )

        from pathtree.actions.reference import ReferenceActionProvider

        self.action_registry.register(
            "resource",
            "reference",
            ReferenceActionProvider(self.node_service),
        )

    @property
    def reference_service(self):
        """Lazily initialize the reference service to protect against mocks."""
        if not hasattr(self, "_reference_service_lazy"):
            from pathtree.database.repository import ResourceReferenceRepository
            from pathtree.services.resource_reference_service import (
                ResourceReferenceService,
            )

            self._reference_service_lazy = ResourceReferenceService(
                self.node_service,
                ResourceReferenceRepository(self.node_service.repository.session),
            )
        return self._reference_service_lazy

    def compose(self) -> ComposeResult:
        """Compose the screen widgets."""
        yield Header()
        yield SearchInput(id="search-input")
        with Horizontal():
            yield NodeTreeView(self.node_service, id="tree-view")
            yield NodeDetailsPanel(id="details-panel")
        yield Static(
            "[bold]VIEW MODE[/bold]  [cyan]a[/cyan] All · [cyan]x[/cyan] Clear · "
            "[cyan]v[/cyan] Empty · [cyan]d[/cyan] Dirs · [cyan]f[/cyan] Files · "
            "[cyan]s[/cyan] Scripts · [cyan]e[/cyan] Execs · [cyan]u[/cyan] URLs · "
            "[cyan]l[/cyan] Profiles · [cyan]m[/cyan] Multi · [cyan]c[/cyan] Custom · "
            "[cyan]y[/cyan] System · [cyan]Esc[/cyan] Cancel",
            id="view-mode-bar",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Focus the tree view on startup and show initial selection."""
        try:
            self.query_one("#view-mode-bar").display = False
        except NoMatches:
            pass
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

    def _update_details_and_selection(self, force_update: bool = False) -> None:
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
            self._last_selected_node_id = None
            return

        # AVOID duplicate updates if selection hasn't changed (avoids mouse lag)
        if not force_update and cursor_node.data == self._last_selected_node_id:
            return

        # Load node details
        node = self.node_service.get_node(cursor_node.data)
        details_panel.update_node(node)
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

    def action_leave_focus(self) -> None:
        """Leave Focus Mode and restore the complete tree, preserving selection."""
        if self._focused_group_id is not None:
            self._focused_group_id = None
            self.refresh_tree(selected_node_id=self._last_selected_node_id)
            self.app.notify("Exited Focus Mode")

    def on_node_tree_view_open_action_menu(
        self, event: NodeTreeView.OpenActionMenu
    ) -> None:
        """Handle 'o' / 'O' key in tree to open Action Menu."""
        self._clear_view_command_mode()
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

        if node.node_kind == "system_group":
            self.app.notify("Managed sections cannot be modified.", severity="error")
            return

        actions = []
        provider = None
        context = None

        # Resolve actions for Workspace Groups
        if node.node_kind == "workspace_group":
            from pathtree.actions.base import ResourceAction

            actions.extend(
                [
                    ResourceAction(
                        id="focus_group",
                        label="Focus Group",
                        description="Focus this workspace group",
                    ),
                    ResourceAction(
                        id="rename_group",
                        label="Rename Group",
                        description="Rename this workspace group",
                    ),
                    ResourceAction(
                        id="dissolve_group",
                        label="Dissolve Group",
                        description="Dissolve group and move workspaces to Root",
                    ),
                ]
            )

        # Resolve provider-specific actions for Resource nodes
        if node.node_kind == "resource":
            provider = self.action_registry.get_provider(
                node.node_kind, node.resource_type
            )
            if provider:
                context = ResourceActionContext(
                    node=node,
                    output_path=self.output_path,
                )
                actions.extend(provider.get_available_actions(context))

            # Dynamically inject Create Reference for any real resource
            if node.resource_type != "reference":
                from pathtree.actions.base import ResourceAction

                actions.append(
                    ResourceAction(
                        id="create_reference",
                        label="Create Reference",
                        description=(
                            "Create a reference to this resource in another "
                            "workspace or folder"
                        ),
                    )
                )

        # Dynamically append dynamic Pin/Unpin actions based on current pin state
        from pathtree.actions.base import ResourceAction

        if self.pin_service:
            is_pinned = self.pin_service.is_pinned(node.id)
            if is_pinned:
                actions.append(
                    ResourceAction(
                        id="unpin_node",
                        label="Unpin Node",
                        description="Remove this node from global pins",
                    )
                )
            else:
                actions.append(
                    ResourceAction(
                        id="pin_node",
                        label="Pin Node",
                        description="Pin this node globally for fast access",
                    )
                )

        def handle_action_menu_finished(result: ActionMenuResult | None) -> None:
            tree.focus()
            if result is not None and result.action_id is not None:
                if result.action_id == "focus_group":
                    self._focused_group_id = node.id
                    self.refresh_tree(selected_node_id=node.id)
                    self.app.notify(f"Focused on group '{node.name}'")
                elif result.action_id == "rename_group":
                    from pathtree.ui.dialogs.edit_node import EditNodeDialog

                    def on_rename_finished(success: bool) -> None:
                        if success:
                            self.app.notify(f"Renamed group to '{node.name}'")
                            self.refresh_tree(selected_node_id=node.id)
                        tree.focus()

                    self.app.push_screen(
                        EditNodeDialog(self.node_service, node.id),
                        callback=on_rename_finished,
                    )
                elif result.action_id == "dissolve_group":
                    self.node_service.dissolve_group(node.id)
                    self.app.notify(
                        f"Dissolved group '{node.name}'. Workspaces moved to Root."
                    )
                    self.refresh_tree()
                elif result.action_id == "pin_node":
                    self.pin_service.pin_node(node.id)
                    self.app.notify(f'Pinned "{node.name}" globally')
                    self.refresh_tree(selected_node_id=node.id)
                elif result.action_id == "unpin_node":
                    self.pin_service.unpin_node(node.id)
                    self.app.notify(f'Unpinned "{node.name}"')
                    self.refresh_tree(selected_node_id=node.id)
                elif result.action_id == "create_reference":
                    from pathtree.ui.dialogs.reference_manager import (
                        ReferenceManagerDialog,
                    )

                    def on_ref_mgr_finished(new_node_id: uuid.UUID | None) -> None:
                        if new_node_id:
                            self.refresh_tree(selected_node_id=new_node_id)
                        tree.focus()

                    self.app.push_screen(
                        ReferenceManagerDialog(
                            self.node_service,
                            self.reference_service,
                            original_node_id=node.id,
                            mode="create",
                        ),
                        callback=on_ref_mgr_finished,
                    )
                elif result.action_id == "reconnect":
                    from pathtree.ui.dialogs.reference_manager import (
                        ReferenceManagerDialog,
                    )

                    def on_ref_mgr_finished(new_node_id: uuid.UUID | None) -> None:
                        if new_node_id:
                            self.refresh_tree(selected_node_id=new_node_id)
                        tree.focus()

                    self.app.push_screen(
                        ReferenceManagerDialog(
                            self.node_service,
                            self.reference_service,
                            reference_node_id=node.id,
                            mode="reconnect",
                        ),
                        callback=on_ref_mgr_finished,
                    )
                elif result.action_id == "copy_reference_to_workspace":
                    from pathtree.ui.dialogs.reference_manager import (
                        ReferenceManagerDialog,
                    )

                    def on_ref_mgr_finished(new_node_id: uuid.UUID | None) -> None:
                        if new_node_id:
                            self.refresh_tree(selected_node_id=new_node_id)
                        tree.focus()

                    self.app.push_screen(
                        ReferenceManagerDialog(
                            self.node_service,
                            self.reference_service,
                            reference_node_id=node.id,
                            mode="copy",
                        ),
                        callback=on_ref_mgr_finished,
                    )
                elif result.action_id == "move_reference_to_workspace":
                    from pathtree.ui.dialogs.reference_manager import (
                        ReferenceManagerDialog,
                    )

                    def on_ref_mgr_finished(new_node_id: uuid.UUID | None) -> None:
                        if new_node_id:
                            self.refresh_tree(selected_node_id=new_node_id)
                        tree.focus()

                    self.app.push_screen(
                        ReferenceManagerDialog(
                            self.node_service,
                            self.reference_service,
                            reference_node_id=node.id,
                            mode="move",
                        ),
                        callback=on_ref_mgr_finished,
                    )
                elif result.action_id == "rename_reference":
                    from pathtree.ui.dialogs.edit_node import EditNodeDialog

                    def on_rename_finished(success: bool) -> None:
                        if success:
                            self.app.notify(f'Updated reference "{node.name}"')
                            self.refresh_tree(selected_node_id=node.id)
                        tree.focus()

                    self.app.push_screen(
                        EditNodeDialog(self.node_service, node.id),
                        callback=on_rename_finished,
                    )
                elif result.action_id == "move_reference":
                    from pathtree.ui.dialogs.move_node import MoveNodeDialog

                    def on_move_finished(success: bool) -> None:
                        if success:
                            self.app.notify(f'Moved reference "{node.name}"')
                            self.refresh_tree(selected_node_id=node.id)
                        tree.focus()

                    self.app.push_screen(
                        MoveNodeDialog(self.node_service, node.id),
                        callback=on_move_finished,
                    )
                else:
                    if provider and context:
                        self.execute_action(result.action_id, provider, context)

        self.app.push_screen(
            ResourceActionMenu(actions, title=f"Actions for {node.name}"),
            callback=handle_action_menu_finished,
        )

    def on_node_tree_view_open_pins_list(
        self, event: NodeTreeView.OpenPinsList
    ) -> None:
        """Handle 'p' key in tree to open the Pins screen."""
        self._clear_view_command_mode()
        from pathtree.ui.screens.pins import PinsScreen

        def handle_pins_screen_finished(selected_node_id: uuid.UUID | None) -> None:
            if selected_node_id is not None:
                # User selected/activated a pin, navigate to and select it in the tree
                self.refresh_tree(selected_node_id=selected_node_id)
            tree = self.query_one("#tree-view", NodeTreeView)
            tree.focus()

        self.app.push_screen(
            PinsScreen(self.node_service, self.pin_service),
            callback=handle_pins_screen_finished,
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

        # Special launch profile creation/view action handler
        if action_id == "create_launch_profile":
            from pathtree.ui.dialogs.edit_profile import EditProfileDialog

            tree = self.query_one("#tree-view", NodeTreeView)

            def handle_create_finished(new_node_id: uuid.UUID | None) -> None:
                if new_node_id is not None:
                    self.app.notify("Launch Profile created successfully.")
                    self.refresh_tree(selected_node_id=new_node_id)
                tree.focus()

            self.app.push_screen(
                EditProfileDialog(
                    self.node_service,
                    self.launch_profile_service,
                    target_node_id=context.node.id,
                ),
                callback=handle_create_finished,
            )
            return

        elif action_id == "view_launch_profiles":
            from pathtree.ui.dialogs.launch_profiles_list import LaunchProfilesScreen

            tree = self.query_one("#tree-view", NodeTreeView)

            def handle_view_finished(res) -> None:
                self.refresh_tree()
                tree.focus()

            self.app.push_screen(
                LaunchProfilesScreen(
                    self.node_service,
                    self.launch_profile_service,
                    target_node_id=context.node.id,
                ),
                callback=handle_view_finished,
            )
            return

        elif action_id == "edit_profile":
            from pathtree.ui.dialogs.edit_profile import EditProfileDialog

            tree = self.query_one("#tree-view", NodeTreeView)
            try:
                profile = self.launch_profile_service.get_profile_for_node(
                    context.node.id
                )

                def handle_edit_finished(updated_node_id: uuid.UUID | None) -> None:
                    if updated_node_id is not None:
                        self.app.notify("Launch Profile updated.")
                        self.refresh_tree(selected_node_id=updated_node_id)
                    tree.focus()

                self.app.push_screen(
                    EditProfileDialog(
                        self.node_service,
                        self.launch_profile_service,
                        profile_id=profile.id,
                    ),
                    callback=handle_edit_finished,
                )
            except Exception as e:
                details_panel.update_error(str(e))
            return

        elif action_id == "reconnect_target":
            from pathtree.ui.dialogs.reconnect_profile import ReconnectTargetDialog

            tree = self.query_one("#tree-view", NodeTreeView)
            try:
                profile = self.launch_profile_service.get_profile_for_node(
                    context.node.id
                )

                def handle_reconnect_finished(changed: bool) -> None:
                    if changed:
                        self.app.notify("Launch Profile reconnected.")
                        self.refresh_tree(selected_node_id=context.node.id)
                    tree.focus()

                self.app.push_screen(
                    ReconnectTargetDialog(
                        self.node_service,
                        self.launch_profile_service,
                        profile_id=profile.id,
                    ),
                    callback=handle_reconnect_finished,
                )
            except Exception as e:
                details_panel.update_error(str(e))
            return

        elif action_id == "delete_profile":
            tree = self.query_one("#tree-view", NodeTreeView)
            try:
                profile = self.launch_profile_service.get_profile_for_node(
                    context.node.id
                )
                self.launch_profile_service.delete_profile(profile.id)
                self.app.notify("Launch Profile deleted.")
                self.refresh_tree()
                tree.focus()
            except Exception as e:
                details_panel.update_error(str(e))
            return

        elif action_id == "edit_launcher":
            from pathtree.ui.dialogs.edit_multi_launcher import EditMultiLauncherDialog

            tree = self.query_one("#tree-view", NodeTreeView)
            try:
                launcher = self.multi_launcher_service.get_launcher_for_node(
                    context.node.id
                )

                def handle_edit_finished(changed: bool) -> None:
                    if changed:
                        self.app.notify("Multi Launcher updated.")
                        self.refresh_tree(selected_node_id=context.node.id)
                    tree.focus()

                self.app.push_screen(
                    EditMultiLauncherDialog(
                        self.node_service,
                        self.launch_profile_service,
                        self.multi_launcher_service,
                        launcher_id=launcher.id,
                    ),
                    callback=handle_edit_finished,
                )
            except Exception as e:
                details_panel.update_error(str(e))
            return

        elif action_id == "duplicate_launcher":
            tree = self.query_one("#tree-view", NodeTreeView)
            try:
                launcher = self.multi_launcher_service.get_launcher_for_node(
                    context.node.id
                )
                new_launcher = self.multi_launcher_service.duplicate_launcher(
                    launcher.id
                )
                self.app.notify(f"Duplicated Multi Launcher '{context.node.name}'")
                self.refresh_tree(selected_node_id=new_launcher.launcher_node_id)
                tree.focus()
            except Exception as e:
                details_panel.update_error(str(e))
            return

        elif action_id == "delete_launcher":
            tree = self.query_one("#tree-view", NodeTreeView)
            try:
                launcher = self.multi_launcher_service.get_launcher_for_node(
                    context.node.id
                )
                self.multi_launcher_service.delete_launcher(launcher.id)
                self.app.notify("Multi Launcher deleted.")
                self.refresh_tree()
                tree.focus()
            except Exception as e:
                details_panel.update_error(str(e))
            return

        result = provider.execute(action_id, context)
        if not result.success:
            err = result.error_message or "Action execution failed."
            details_panel.update_error(err)
            return

        if result.message:
            self.app.notify(result.message)

        # Handle specific return outputs from Reference provider
        if (
            context.node.node_kind == "resource"
            and context.node.resource_type == "reference"
        ):
            if (
                action_id in ("open", "locate_original")
                and result.output_value is not None
            ):
                target_orig_id = result.output_value
                if action_id == "open":
                    self.activate_node(target_orig_id)
                elif action_id == "locate_original":
                    self.refresh_tree(selected_node_id=target_orig_id)
                return

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

        # --- Automatic delegation of Reference nodes to their original targets ---
        if node.node_kind == "resource" and node.resource_type == "reference":
            ref = self.reference_service.get_reference_by_node_id(node_id)
            if not ref or ref.original_node_id is None:
                details_panel.update_error("Broken Reference")
                return
            orig_node = self.node_service.get_node(ref.original_node_id)
            if not orig_node:
                details_panel.update_error("Broken Reference")
                return
            self.activate_node(orig_node.id)
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

        # Prune filtered nodes to show only focused group and its descendants if focus is active
        if self._focused_group_id is not None:
            filtered_nodes = [
                tn for tn in filtered_nodes if tn.node.id == self._focused_group_id
            ]

        # Apply Workspace View Settings filtering on the tree nodes
        if self.view_settings_service:
            filtered_nodes = self.view_settings_service.filter_tree(filtered_nodes)

        is_now_non_empty = bool(self._last_query.strip())

        # Build list of visible IDs in the filtered tree
        visible_ids = []

        def gather_ids(t_nodes):
            for tn in t_nodes:
                visible_ids.append(tn.node.id)
                gather_ids(tn.children)

        gather_ids(filtered_nodes)

        def find_nearest_visible_ancestor(
            node_id: uuid.UUID | None,
        ) -> uuid.UUID | None:
            if not node_id:
                return None
            curr_id = node_id
            visited = set()
            while curr_id is not None:
                if curr_id in visited:
                    break
                visited.add(curr_id)
                if curr_id in visible_ids:
                    return curr_id
                node = self.node_service.get_node(curr_id)
                if not node:
                    break
                curr_id = node.parent_id
            return None

        # Selection fallback logic
        target_id = None
        if selected_node_id is not None:
            if selected_node_id in visible_ids:
                target_id = selected_node_id
            else:
                # Find nearest visible ancestor if selected node becomes hidden
                target_id = find_nearest_visible_ancestor(selected_node_id)

        if target_id is None and fallback_node_id is not None:
            if fallback_node_id in visible_ids:
                target_id = fallback_node_id
            else:
                target_id = find_nearest_visible_ancestor(fallback_node_id)

        if target_id is None and visible_ids:
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

        # Resolve current workspace context to apply auto-expand logic
        current_workspace_id = None
        if target_id is not None:
            current_workspace_id = self.node_service.resolve_workspace_context(
                target_id
            )

        # Auto-expand active filter sections for the current workspace context
        if self.view_settings_service and current_workspace_id:
            settings = self.view_settings_service.get_settings(current_workspace_id)
            if settings.current_mode == "filter":
                expanded_node_ids.add(current_workspace_id)

                ws_tn = None
                for tn in filtered_nodes:
                    if tn.node.id == current_workspace_id:
                        ws_tn = tn
                        break

                if ws_tn:
                    from pathtree.services.workspace_view_settings_service import CUSTOM

                    for child in ws_tn.children:
                        if child.node.node_kind == "system_group":
                            if child.node.system_role == "system":
                                has_res_filters = bool(
                                    settings.last_filter_mask & ~CUSTOM
                                )
                                if has_res_filters:
                                    expanded_node_ids.add(child.node.id)
                                    for sub in child.children:
                                        expanded_node_ids.add(sub.node.id)
                            elif child.node.system_role == "custom":
                                if settings.show_custom:
                                    expanded_node_ids.add(child.node.id)

        # Get active filter workspace IDs from top-level loaded
        # workspace nodes in memory
        active_filter_workspace_ids = set()
        if self.view_settings_service:
            for tn in filtered_nodes:
                if tn.node.node_kind == "workspace":
                    if self.view_settings_service.has_active_filter(tn.node.id):
                        active_filter_workspace_ids.add(tn.node.id)

        # Reload tree in the widget
        tree.load_tree(
            filtered_nodes,
            selected_node_id=target_id,
            expand_all=is_now_non_empty,
            expanded_node_ids=expanded_node_ids,
            active_filter_workspace_ids=active_filter_workspace_ids,
        )

        if not filtered_nodes and is_now_non_empty:
            tree.move_cursor(None)

        self.call_after_refresh(
            lambda: self._update_details_and_selection(force_update=True)
        )

    def on_node_tree_view_focus_search(self, event: NodeTreeView.FocusSearch) -> None:
        """Focus SearchInput when '/' or 's' is pressed in the tree."""
        search_input = self.query_one("#search-input", SearchInput)
        search_input.focus()

    def on_node_tree_view_add_node(self, event: NodeTreeView.AddNode) -> None:
        """Handle 'a' key in tree to open Add Node Dialog."""
        self._clear_view_command_mode()
        tree = self.query_one("#tree-view", NodeTreeView)

        # Capture expansion state before opening the dialog
        captured_expanded_node_ids = tree.get_expanded_node_ids()

        # autoritative workspace context resolution
        selected_node_id = tree.cursor_node.data if tree.cursor_node else None
        current_workspace_id = self.node_service.resolve_workspace_context(
            selected_node_id
        )

        # Default parent behavior matching legacy expectations
        default_parent_id = None
        if tree.cursor_node is not None and tree.cursor_node.data is not None:
            node = self.node_service.get_node(tree.cursor_node.data)
            if node is not None:
                if node.node_kind in ("workspace", "folder"):
                    default_parent_id = node.id
                elif node.node_kind == "resource":
                    default_parent_id = node.parent_id
                else:
                    default_parent_id = node.id

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
            AddNodeDialog(
                self.node_service,
                workspace_id=current_workspace_id,
                default_parent_id=default_parent_id,
            ),
            callback=handle_add_finished,
        )

    def on_node_tree_view_edit_node(self, event: NodeTreeView.EditNode) -> None:
        """Handle 'e' key in tree to open Edit Node Dialog."""
        self._clear_view_command_mode()
        tree = self.query_one("#tree-view", NodeTreeView)
        if tree.cursor_node is None or tree.cursor_node.data is None:
            return

        node_id = tree.cursor_node.data
        node = self.node_service.get_node(node_id)
        if node is not None and node.node_kind == "system_group":
            self.app.notify("Managed sections cannot be edited.", severity="error")
            return

        # Capture expansion state before opening the dialog
        captured_expanded_node_ids = tree.get_expanded_node_ids()
        if (
            node is not None
            and node.node_kind == "resource"
            and node.resource_type == "launch_profile"
        ):
            from pathtree.ui.dialogs.edit_profile import EditProfileDialog

            try:
                profile = self.launch_profile_service.get_profile_for_node(node_id)

                def handle_profile_edit_finished(
                    updated_node_id: uuid.UUID | None,
                ) -> None:
                    if updated_node_id is not None:
                        self.app.notify("Launch Profile updated.")
                        self.refresh_tree(selected_node_id=updated_node_id)
                    tree.focus()

                self.app.push_screen(
                    EditProfileDialog(
                        self.node_service,
                        self.launch_profile_service,
                        profile_id=profile.id,
                    ),
                    callback=handle_profile_edit_finished,
                )
            except Exception as e:
                details_panel = self.query_one("#details-panel", NodeDetailsPanel)
                details_panel.update_error(str(e))
            return

        elif (
            node is not None
            and node.node_kind == "resource"
            and node.resource_type == "multi_launcher"
        ):
            from pathtree.ui.dialogs.edit_multi_launcher import (
                EditMultiLauncherDialog,
            )

            try:
                launcher = self.multi_launcher_service.get_launcher_for_node(node_id)

                def handle_launcher_edit_finished(changed: bool) -> None:
                    if changed:
                        self.app.notify("Multi Launcher updated.")
                        self.refresh_tree(selected_node_id=node_id)
                    tree.focus()

                self.app.push_screen(
                    EditMultiLauncherDialog(
                        self.node_service,
                        self.launch_profile_service,
                        self.multi_launcher_service,
                        launcher_id=launcher.id,
                    ),
                    callback=handle_launcher_edit_finished,
                )
            except Exception as e:
                details_panel = self.query_one("#details-panel", NodeDetailsPanel)
                details_panel.update_error(str(e))
            return

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
        self._clear_view_command_mode()
        tree = self.query_one("#tree-view", NodeTreeView)
        if tree.cursor_node is None or tree.cursor_node.data is None:
            return

        node_id = tree.cursor_node.data
        node = self.node_service.get_node(node_id)
        if node is not None and node.node_kind == "system_group":
            self.app.notify("Managed sections cannot be moved.", severity="error")
            return

        # Capture expansion state before opening the dialog
        captured_expanded_node_ids = tree.get_expanded_node_ids()

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
        self._clear_view_command_mode()
        tree = self.query_one("#tree-view", NodeTreeView)
        if tree.cursor_node is None or tree.cursor_node.data is None:
            return

        node_id = tree.cursor_node.data
        node = self.node_service.get_node(node_id)
        if node is None:
            return

        if node.node_kind == "system_group":
            self.app.notify("Managed sections cannot be deleted.", severity="error")
            return

        if node.node_kind == "workspace_group":
            self.node_service.dissolve_group(node.id)
            self.app.notify(f"Dissolved group '{node.name}'. Workspaces moved to Root.")
            self.refresh_tree()
            return

        # Capture expansion state before opening the dialog
        captured_expanded_node_ids = tree.get_expanded_node_ids()

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

    def _clear_view_command_mode(self) -> None:
        """Clear the active View Command Mode and restore the standard footer."""
        self._view_command_active = False
        try:
            self.query_one("#view-mode-bar").display = False
            self.query_one("Footer").display = True
        except NoMatches:
            pass

    def on_blur(self, event: events.Blur) -> None:
        """Clear View Command Mode when MainScreen loses focus."""
        self._clear_view_command_mode()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """Cancel View Command Mode if a text input widget gets focused."""
        if getattr(self, "_view_command_active", False):
            widget = event.control
            inputs = ("Input", "SearchInput", "HistoryInput", "PathAutocomplete")
            if widget and widget.__class__.__name__ in inputs:
                self._clear_view_command_mode()

    def on_key(self, event: events.Key) -> None:
        """Handle key events to support the View Command Mode state machine."""
        if self.view_settings_service is None:
            return

        # 1. Check if view command mode is active
        if getattr(self, "_view_command_active", False):
            event.stop()
            event.prevent_default()

            key = event.key

            if key == "escape":
                self._clear_view_command_mode()
                self.app.notify("View command canceled.")
                return

            valid_keys = {"a", "x", "v", "d", "f", "s", "e", "u", "l", "m", "c", "y"}
            if key in valid_keys:
                self._clear_view_command_mode()
                self._handle_view_command(key)
            else:
                self.app.notify(f"Unknown View command: {key}", severity="error")
            return

        # 2. Check if the key is the prefix 'v'
        focused = self.app.focused
        inputs = ("Input", "SearchInput", "HistoryInput", "PathAutocomplete")
        if focused and focused.__class__.__name__ in inputs:
            return

        if event.key == "v":
            event.stop()
            event.prevent_default()

            tree = self.query_one("#tree-view", NodeTreeView)
            selected_node_id = tree.cursor_node.data if tree.cursor_node else None
            workspace_id = self.node_service.resolve_workspace_context(selected_node_id)
            if not workspace_id:
                self.app.notify("No workspace selected.", severity="error")
                return

            self._view_command_active = True
            try:
                self.query_one("#view-mode-bar").display = True
                self.query_one("Footer").display = False
            except NoMatches:
                pass

    def _handle_view_command(self, key: str) -> None:
        """Handle the completed View sequence subkey."""
        tree = self.query_one("#tree-view", NodeTreeView)
        selected_node_id = tree.cursor_node.data if tree.cursor_node else None
        workspace_id = self.node_service.resolve_workspace_context(selected_node_id)

        if not workspace_id:
            self.app.notify("No active workspace context.", severity="error")
            return

        settings = self.view_settings_service.get_settings(workspace_id)

        # Import bits
        from pathtree.services.workspace_view_settings_service import (
            CUSTOM,
            DIRECTORIES,
            EXECUTABLES,
            FILES,
            LAUNCH_PROFILES,
            MULTI_LAUNCHERS,
            SCRIPTS,
            URLS,
        )

        bit_map = {
            "d": DIRECTORIES,
            "f": FILES,
            "s": SCRIPTS,
            "e": EXECUTABLES,
            "u": URLS,
            "l": LAUNCH_PROFILES,
            "m": MULTI_LAUNCHERS,
        }

        notif_vv = False
        notif_vx = False

        if key == "a":
            # va: Toggle All View <-> Last Filter View
            if settings.current_mode == "all":
                # Only switch if a non-default filter is stored
                has_stored = (
                    settings.last_filter_mask > 0
                    or not settings.show_custom
                    or not settings.show_system
                )
                if has_stored:
                    settings.current_mode = "filter"
            else:
                settings.current_mode = "all"

        elif key == "x":
            # vx: Delete stored filter
            settings = self.view_settings_service.clear_settings(workspace_id)
            notif_vx = True

        elif key == "v":
            # vv: Toggle hide empty
            settings.hide_empty_sections = not settings.hide_empty_sections
            notif_vv = True

        elif key in bit_map:
            # Resource toggles
            bit = bit_map[key]
            if settings.current_mode == "all":
                settings.current_mode = "filter"
                settings.last_filter_mask = bit
                settings.show_custom = False
                settings.show_system = True
            else:
                settings.last_filter_mask ^= bit
                # Safety return to All View if no filters left
                has_res = bool(settings.last_filter_mask & ~CUSTOM)
                if not has_res and not settings.show_custom:
                    settings.current_mode = "all"
                    settings.last_filter_mask = 0
                    settings.show_system = True
                    settings.show_custom = True

        elif key == "c":
            # vc: Toggle custom
            if settings.current_mode == "all":
                settings.current_mode = "filter"
                settings.last_filter_mask = 0
                settings.show_custom = True
                settings.show_system = False
            else:
                settings.show_custom = not settings.show_custom
                has_res = bool(settings.last_filter_mask & ~CUSTOM)
                if not settings.show_custom and not has_res:
                    settings.current_mode = "all"
                    settings.last_filter_mask = 0
                    settings.show_system = True
                    settings.show_custom = True

        elif key == "y":
            # vy: Toggle System-only mode
            if settings.current_mode == "all":
                settings.current_mode = "filter"
                settings.last_filter_mask = 0
                settings.show_system = True
                settings.show_custom = False
            else:
                # Toggle between System-only and both
                if settings.show_system and not settings.show_custom:
                    settings.show_custom = True
                else:
                    settings.show_system = True
                    settings.show_custom = False

        else:
            self.app.notify(f"Invalid view command subkey: {key}", severity="error")
            return

        # Save settings & Notify & Refresh
        self.view_settings_service.save_settings(settings)

        if notif_vv:
            status = "Hidden" if settings.hide_empty_sections else "Visible"
            self.app.notify(f"Empty sections: {status}")
        elif notif_vx:
            self.app.notify("Saved workspace view cleared.")
        else:
            self._notify_view_state(settings)

        self.refresh_tree(selected_node_id=selected_node_id)

    def _notify_view_state(self, settings) -> None:
        """Show a short notification describing the active View settings."""
        from pathtree.services.workspace_view_settings_service import CUSTOM

        if settings.current_mode == "all":
            self.app.notify("View: All")
            return

        # Filter View
        # Check Custom & System visibility
        has_res_filters = bool(settings.last_filter_mask & ~CUSTOM)
        show_custom = settings.show_custom
        show_system = settings.show_system or has_res_filters

        if show_custom and not show_system:
            self.app.notify("View: Custom only")
            return
        if not show_custom and show_system and not has_res_filters:
            self.app.notify("View: System only")
            return

        # Construct specific group list
        active_groups = []
        if has_res_filters:
            from pathtree.services.workspace_view_settings_service import (
                DIRECTORIES,
                EXECUTABLES,
                FILES,
                LAUNCH_PROFILES,
                MULTI_LAUNCHERS,
                SCRIPTS,
                URLS,
            )

            mask = settings.last_filter_mask
            if mask & DIRECTORIES:
                active_groups.append("Directories")
            if mask & FILES:
                active_groups.append("Files")
            if mask & SCRIPTS:
                active_groups.append("Scripts")
            if mask & EXECUTABLES:
                active_groups.append("Executables")
            if mask & URLS:
                active_groups.append("URLs")
            if mask & LAUNCH_PROFILES:
                active_groups.append("Launch Profiles")
            if mask & MULTI_LAUNCHERS:
                active_groups.append("Multi Launchers")
        else:
            if show_system:
                active_groups.append("System")

        if show_custom:
            active_groups.append("Custom")

        if active_groups:
            self.app.notify(f"View: {', '.join(active_groups)}")
