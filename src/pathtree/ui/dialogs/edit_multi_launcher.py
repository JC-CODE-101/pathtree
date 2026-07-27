import uuid
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DataTable, Input, Label, Static

from pathtree.services.launch_profile_service import LaunchProfileService
from pathtree.services.multi_launcher_service import (
    MultiLauncherService,
)
from pathtree.services.node_service import NodeService


class AddProfileSelectScreen(ModalScreen[uuid.UUID | None]):
    """Modal screen to choose a launch profile to add to the Multi Launcher."""

    CSS = """
    AddProfileSelectScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #select-container {
        width: 50;
        height: 15;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }

    .select-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    #select-table {
        height: 1fr;
        border: none;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close_cancel", "Cancel", show=True),
        Binding("enter", "select_current", "Select", show=True),
    ]

    def __init__(
        self,
        node_service: NodeService,
        launch_profile_service: LaunchProfileService,
        workspace_id: uuid.UUID,
    ) -> None:
        super().__init__()
        self.node_service = node_service
        self.launch_profile_service = launch_profile_service
        self.workspace_id = workspace_id
        self._profiles_map: list[uuid.UUID] = []

    def compose(self) -> ComposeResult:
        with Container(id="select-container"):
            yield Label("Select Launch Profile to Add", classes="select-title")
            yield DataTable(id="select-table")

    def on_mount(self) -> None:
        table = self.query_one("#select-table", DataTable)
        table.cursor_type = "row"
        table.add_column("Profile Name", width=25)
        table.add_column("Target", width=20)

        profiles = self.launch_profile_service.list_profiles_for_workspace(
            self.workspace_id
        )
        for p in profiles:
            p_node = self.node_service.get_node(p.profile_node_id)
            if p_node:
                t_node = (
                    self.node_service.get_node(p.target_node_id)
                    if p.target_node_id
                    else None
                )
                t_name = t_node.name if t_node else "Detached"
                table.add_row(p_node.name, t_name)
                self._profiles_map.append(p.id)

        if self._profiles_map:
            table.focus()
            table.move_cursor(row=0)

    def action_close_cancel(self) -> None:
        self.dismiss(None)

    def action_select_current(self) -> None:
        table = self.query_one("#select-table", DataTable)
        row = table.cursor_row
        if row is not None and 0 <= row < len(self._profiles_map):
            self.dismiss(self._profiles_map[row])
        else:
            self.dismiss(None)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.action_select_current()


class EditMultiLauncherDialog(ModalScreen[bool]):
    """Modal screen for editing a Multi Launcher and managing its items."""

    CSS = """
    EditMultiLauncherDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #dialog-container {
        width: 80;
        height: 32;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }

    .title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }

    .form-row {
        height: auto;
        margin-bottom: 1;
    }

    .field-container {
        margin-bottom: 1;
        height: auto;
    }

    .field-label {
        text-style: bold;
        margin-bottom: 0;
    }

    #launcher-table {
        height: 14;
        border: none;
    }

    .sidebar-buttons {
        width: 18;
        height: auto;
        margin-left: 2;
    }

    .sidebar-buttons Button {
        width: 100%;
        margin-bottom: 0;
    }

    #status-area {
        height: 2;
        margin-top: 1;
        color: $error;
        text-style: bold;
    }

    .bottom-buttons {
        align: right middle;
        margin-top: 1;
        height: auto;
    }

    .bottom-buttons Button {
        margin-left: 2;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "cancel_close", "Close", show=True),
    ]

    def __init__(
        self,
        node_service: NodeService,
        launch_profile_service: LaunchProfileService,
        multi_launcher_service: MultiLauncherService,
        launcher_id: uuid.UUID,
    ) -> None:
        super().__init__()
        self.node_service = node_service
        self.launch_profile_service = launch_profile_service
        self.multi_launcher_service = multi_launcher_service
        self.launcher_id = launcher_id
        self.launcher = self.multi_launcher_service.get_launcher(launcher_id)
        self._items_map: list[uuid.UUID] = []
        self._changed = False

    def compose(self) -> ComposeResult:
        with Container(id="dialog-container"):
            yield Label(f"Edit Multi Launcher: {self.launcher.name}", classes="title")

            with Horizontal(classes="form-row"):
                with Vertical(classes="field-container", id="name-container"):
                    yield Label("Name *", classes="field-label")
                    yield Input(
                        value=self.launcher.name,
                        placeholder="Enter name...",
                        id="input-name",
                    )
                with Vertical(classes="field-container", id="desc-container"):
                    yield Label("Description", classes="field-label")
                    yield Input(
                        value=self.launcher.description or "",
                        placeholder="Enter description...",
                        id="input-description",
                    )

            with Horizontal():
                yield DataTable(id="launcher-table")
                with Vertical(classes="sidebar-buttons"):
                    yield Button("Add Profile", id="btn-add")
                    yield Button("Remove Profile", id="btn-remove")
                    yield Button("Move Up", id="btn-up")
                    yield Button("Move Down", id="btn-down")
                    yield Button("Enable/Disable", id="btn-toggle")
                    yield Button("Set Delay", id="btn-delay")

            yield Static("", id="status-area")

            with Horizontal(classes="bottom-buttons"):
                yield Button("Run", variant="success", id="btn-run")
                yield Button("Close", variant="primary", id="btn-close")

    def on_mount(self) -> None:
        table = self.query_one("#launcher-table", DataTable)
        table.cursor_type = "row"
        table.add_column("Pos", width=5)
        table.add_column("Profile Name", width=25)
        table.add_column("Status", width=10)
        table.add_column("Delay (ms)", width=12)

        self.reload_items()
        table.focus()

    def reload_items(self, select_row_idx: int = 0) -> None:
        table = self.query_one("#launcher-table", DataTable)
        table.clear()
        self._items_map = []

        items = self.multi_launcher_service.repository.list_items_for_launcher(
            self.launcher_id
        )
        for idx, item in enumerate(items):
            try:
                profile = self.launch_profile_service.get_profile(
                    item.launch_profile_id
                )
                p_node = self.node_service.get_node(profile.profile_node_id)
                p_name = p_node.name if p_node else "Unknown"
            except Exception:
                p_name = "Unknown"

            status_str = "ENABLED" if item.enabled else "DISABLED"
            table.add_row(str(idx + 1), p_name, status_str, f"{item.delay_ms} ms")
            self._items_map.append(item.id)

        if self._items_map:
            safe_row = max(0, min(select_row_idx, len(self._items_map) - 1))
            table.move_cursor(row=safe_row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id
        status_area = self.query_one("#status-area", Static)
        status_area.update("")

        if btn_id == "btn-close":
            self.save_launcher_details_and_close()
        elif btn_id == "btn-run":
            self.run_multi_launcher()
        elif btn_id == "btn-add":
            self.add_profile_flow()
        elif btn_id == "btn-remove":
            self.remove_selected_item()
        elif btn_id == "btn-up":
            self.move_selected_item("up")
        elif btn_id == "btn-down":
            self.move_selected_item("down")
        elif btn_id == "btn-toggle":
            self.toggle_selected_item()
        elif btn_id == "btn-delay":
            self.set_selected_item_delay()

    def save_launcher_details_and_close(self) -> None:
        status_area = self.query_one("#status-area", Static)
        name = self.query_one("#input-name", Input).value.strip()
        description = self.query_one("#input-description", Input).value.strip() or None

        if not name:
            status_area.update("Multi Launcher Name is required.")
            return

        try:
            self.multi_launcher_service.update_launcher(
                self.launcher_id, name=name, description=description
            )
            self.dismiss(True)
        except Exception as e:
            status_area.update(str(e))

    def action_cancel_close(self) -> None:
        self.save_launcher_details_and_close()

    def run_multi_launcher(self) -> None:
        try:
            self.multi_launcher_service.execute_launcher(self.launcher_id)
            self.app.notify("Multi Launcher run completed successfully!")
            self.dismiss(True)
        except Exception as e:
            self.app.notify(f"Execution failed: {e}", severity="error")

    def add_profile_flow(self) -> None:
        def handle_profile_selected(profile_id: uuid.UUID | None) -> None:
            if profile_id:
                self.multi_launcher_service.add_item(self.launcher_id, profile_id)
                self._changed = True
                self.reload_items(select_row_idx=len(self._items_map))
            self.query_one("#launcher-table", DataTable).focus()

        self.app.push_screen(
            AddProfileSelectScreen(
                self.node_service,
                self.launch_profile_service,
                self.launcher.workspace_id,
            ),
            callback=handle_profile_selected,
        )

    def remove_selected_item(self) -> None:
        table = self.query_one("#launcher-table", DataTable)
        row = table.cursor_row
        if row is not None and 0 <= row < len(self._items_map):
            item_id = self._items_map[row]
            self.multi_launcher_service.remove_item(item_id)
            self._changed = True
            self.reload_items(select_row_idx=row)

    def move_selected_item(self, direction: str) -> None:
        table = self.query_one("#launcher-table", DataTable)
        row = table.cursor_row
        if row is not None and 0 <= row < len(self._items_map):
            item_id = self._items_map[row]
            self.multi_launcher_service.reorder_item(item_id, direction)
            self._changed = True
            target_row = row - 1 if direction == "up" else row + 1
            self.reload_items(select_row_idx=target_row)

    def toggle_selected_item(self) -> None:
        table = self.query_one("#launcher-table", DataTable)
        row = table.cursor_row
        if row is not None and 0 <= row < len(self._items_map):
            item_id = self._items_map[row]
            # Fetch current
            item = self.multi_launcher_service.repository.get_item_by_id(item_id)
            if item:
                self.multi_launcher_service.set_item_enabled(item_id, not item.enabled)
                self._changed = True
                self.reload_items(select_row_idx=row)

    def set_selected_item_delay(self) -> None:
        table = self.query_one("#launcher-table", DataTable)
        row = table.cursor_row
        if row is not None and 0 <= row < len(self._items_map):
            item_id = self._items_map[row]
            item = self.multi_launcher_service.repository.get_item_by_id(item_id)
            if not item:
                return

            # Simple dialog/prompt to get delay ms
            class DelayPromptScreen(ModalScreen[int | None]):
                CSS = """
                DelayPromptScreen {
                    align: center middle;
                    background: rgba(0, 0, 0, 0.5);
                }
                #prompt-container {
                    width: 40;
                    height: auto;
                    background: $panel;
                    border: thick $accent;
                    padding: 1 2;
                }
                .prompt-label {
                    text-style: bold;
                    margin-bottom: 1;
                }
                .prompt-buttons {
                    align: right middle;
                    margin-top: 1;
                    height: auto;
                }
                .prompt-buttons Button {
                    margin-left: 2;
                }
                """

                def __init__(self, initial_value: int) -> None:
                    super().__init__()
                    self.initial_value = initial_value

                def compose(self) -> ComposeResult:
                    with Container(id="prompt-container"):
                        yield Label(
                            "Enter Delay (milliseconds)",
                            classes="prompt-label",
                        )
                        yield Input(
                            value=str(self.initial_value),
                            placeholder="e.g. 1000",
                            id="input-delay-prompt",
                        )
                        yield Static("", id="prompt-error")
                        with Horizontal(classes="prompt-buttons"):
                            yield Button("Cancel", id="btn-prompt-cancel")
                            yield Button("OK", id="btn-prompt-ok")

                def on_button_pressed(self, event: Button.Pressed) -> None:
                    if event.button.id == "btn-prompt-cancel":
                        self.dismiss(None)
                    elif event.button.id == "btn-prompt-ok":
                        self.submit_val()

                def submit_val(self) -> None:
                    val_str = self.query_one("#input-delay-prompt", Input).value.strip()
                    try:
                        val = int(val_str)
                        if val < 0:
                            raise ValueError
                        self.dismiss(val)
                    except ValueError:
                        self.query_one("#prompt-error", Static).update(
                            "Delay must be a positive integer."
                        )

                def on_key(self, event) -> None:
                    if event.key == "enter":
                        event.prevent_default()
                        event.stop()
                        self.submit_val()
                    elif event.key == "escape":
                        event.prevent_default()
                        event.stop()
                        self.dismiss(None)

            def handle_delay_finished(new_delay: int | None) -> None:
                if new_delay is not None:
                    self.multi_launcher_service.set_item_delay(item_id, new_delay)
                    self._changed = True
                    self.reload_items(select_row_idx=row)
                table.focus()

            self.app.push_screen(
                DelayPromptScreen(item.delay_ms), callback=handle_delay_finished
            )
