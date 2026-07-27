import uuid
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label

from pathtree.services.launch_profile_service import (
    LaunchProfileService,
    LaunchProfileServiceError,
)
from pathtree.services.node_service import NodeService
from pathtree.ui.dialogs.edit_profile import EditProfileDialog
from pathtree.ui.dialogs.reconnect_profile import ReconnectTargetDialog


class LaunchProfilesScreen(ModalScreen[None]):
    """Modal screen displaying launch profiles for a Script or Executable.

    Supports running a profile via Enter, editing via 'e', reconnecting via 'r',
    deleting via 'x', and closing via 'q' / Escape.
    """

    CSS = """
    LaunchProfilesScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #profiles-container {
        width: 100;
        height: 30;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }

    .profiles-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        border-bottom: solid $accent;
        padding-bottom: 1;
    }

    #profiles-table {
        height: 1fr;
        border: none;
    }

    .profiles-help {
        text-align: center;
        text-style: italic;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close_screen", "Close", show=True),
        Binding("q", "close_screen", "Close", show=False),
        Binding("enter", "run_profile", "Run Profile", show=True),
        Binding("e", "edit_profile", "Edit", show=True),
        Binding("r", "reconnect_profile", "Reconnect", show=True),
        Binding("x", "delete_profile", "Delete", show=True),
        Binding("j", "cursor_down", "Nav Down", show=False),
        Binding("k", "cursor_up", "Nav Up", show=False),
    ]

    def __init__(
        self,
        node_service: NodeService,
        launch_profile_service: LaunchProfileService,
        target_node_id: uuid.UUID,
    ) -> None:
        super().__init__()
        self.node_service = node_service
        self.launch_profile_service = launch_profile_service
        self.target_node_id = target_node_id
        self._row_profile_ids: list[uuid.UUID] = []

    def compose(self) -> ComposeResult:
        target_node = self.node_service.get_node(self.target_node_id)
        target_name = target_node.name if target_node else "Unknown"

        with Container(id="profiles-container"):
            yield Label(
                f"Launch Profiles for '{target_name}'", classes="profiles-title"
            )
            yield DataTable(id="profiles-table")
            yield Label(
                "[Enter] Run | [e] Edit | [r] Reconnect | [x] Delete | [Esc/q] Close",
                classes="profiles-help",
            )

    def on_mount(self) -> None:
        table = self.query_one("#profiles-table", DataTable)
        table.cursor_type = "row"
        table.add_column("Profile Name", width=25)
        table.add_column("Arguments", width=30)
        table.add_column("Working Dir", width=15)
        table.add_column("Terminal Mode", width=12)
        table.add_column("Status", width=10)
        self.reload_profiles()
        table.focus()

    def reload_profiles(self, select_row_idx: int = 0) -> None:
        table = self.query_one("#profiles-table", DataTable)
        table.clear()
        self._row_profile_ids = []

        profiles = self.launch_profile_service.list_profiles_for_target(
            self.target_node_id
        )
        for profile in profiles:
            profile_node = self.node_service.get_node(profile.profile_node_id)
            if profile_node is None:
                continue

            name = profile_node.name
            args_str = " ".join(profile.argv) if profile.argv else "None"

            wd_name = "None"
            if profile.working_directory_node_id:
                wd_node = self.node_service.get_node(profile.working_directory_node_id)
                if wd_node:
                    wd_name = wd_node.name

            table.add_row(
                name,
                args_str,
                wd_name,
                profile.terminal_mode,
                profile.status.upper(),
            )
            self._row_profile_ids.append(profile.id)

        if self._row_profile_ids:
            safe_row_idx = max(0, min(select_row_idx, len(self._row_profile_ids) - 1))
            table.move_cursor(row=safe_row_idx)

    def action_close_screen(self) -> None:
        self.dismiss(None)

    def action_run_profile(self) -> None:
        table = self.query_one("#profiles-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self._row_profile_ids):
            profile_id = self._row_profile_ids[cursor_row]
            profile = self.launch_profile_service.get_profile(profile_id)
            if profile.status != "active":
                self.app.notify(
                    "Cannot execute a detached launch profile.", severity="error"
                )
                return

            try:
                self.launch_profile_service.execute_profile(profile_id)
                profile_node = self.node_service.get_node(profile.profile_node_id)
                name = profile_node.name if profile_node else "Profile"
                self.app.notify(f"Launched profile '{name}' successfully.")
                self.dismiss(None)
            except LaunchProfileServiceError as e:
                self.app.notify(f"Execution failed: {e}", severity="error")

    def action_edit_profile(self) -> None:
        table = self.query_one("#profiles-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self._row_profile_ids):
            profile_id = self._row_profile_ids[cursor_row]

            def handle_edit_finished(changed: bool) -> None:
                if changed:
                    self.app.notify("Launch Profile updated.")
                self.reload_profiles(select_row_idx=cursor_row)
                table.focus()

            self.app.push_screen(
                EditProfileDialog(
                    self.node_service,
                    self.launch_profile_service,
                    profile_id=profile_id,
                ),
                callback=handle_edit_finished,
            )

    def action_reconnect_profile(self) -> None:
        table = self.query_one("#profiles-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self._row_profile_ids):
            profile_id = self._row_profile_ids[cursor_row]

            def handle_reconnect_finished(changed: bool) -> None:
                if changed:
                    self.app.notify("Launch Profile reconnected successfully.")
                self.reload_profiles(select_row_idx=cursor_row)
                table.focus()

            self.app.push_screen(
                ReconnectTargetDialog(
                    self.node_service,
                    self.launch_profile_service,
                    profile_id=profile_id,
                ),
                callback=handle_reconnect_finished,
            )

    def action_delete_profile(self) -> None:
        table = self.query_one("#profiles-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self._row_profile_ids):
            profile_id = self._row_profile_ids[cursor_row]
            self.launch_profile_service.delete_profile(profile_id)
            self.app.notify("Launch Profile deleted.")
            self.reload_profiles(select_row_idx=cursor_row)

    def action_cursor_down(self) -> None:
        table = self.query_one("#profiles-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and cursor_row < len(self._row_profile_ids) - 1:
            table.move_cursor(row=cursor_row + 1)

    def action_cursor_up(self) -> None:
        table = self.query_one("#profiles-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and cursor_row > 0:
            table.move_cursor(row=cursor_row - 1)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_run_profile()

    def on_key(self, event) -> None:
        key = event.key.lower()
        if key in ("escape", "q"):
            event.prevent_default()
            event.stop()
            self.action_close_screen()
        elif key == "enter":
            event.prevent_default()
            event.stop()
            self.action_run_profile()
        elif key == "e":
            event.prevent_default()
            event.stop()
            self.action_edit_profile()
        elif key == "r":
            event.prevent_default()
            event.stop()
            self.action_reconnect_profile()
        elif key == "x":
            event.prevent_default()
            event.stop()
            self.action_delete_profile()
