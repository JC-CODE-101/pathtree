import shlex
import uuid

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, RadioButton, RadioSet, Select, Static

from pathtree.services.launch_profile_service import (
    LaunchProfileService,
    LaunchProfileServiceError,
)
from pathtree.services.node_service import NodeService
from pathtree.ui.compat import resolve_optional_uuid


class EditProfileDialog(ModalScreen[bool]):
    """Dialog for creating or editing a Launch Profile."""

    CSS = """
    EditProfileDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #dialog-container {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }

    .title {
        text-align: center;
        text-style: bold;
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

    #status-area {
        height: 3;
        margin-top: 1;
        color: $error;
        text-style: bold;
    }

    .buttons-container {
        align: right middle;
        margin-top: 1;
        height: auto;
    }

    Button {
        margin-left: 2;
    }
    """

    def __init__(
        self,
        node_service: NodeService,
        launch_profile_service: LaunchProfileService,
        target_node_id: uuid.UUID | None = None,
        profile_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__()
        self.node_service = node_service
        self.launch_profile_service = launch_profile_service
        self.target_node_id = target_node_id
        self.profile_id = profile_id

        # If editing, load original profile
        self.profile = None
        if self.profile_id:
            self.profile = self.launch_profile_service.get_profile(self.profile_id)
            self.target_node_id = self.profile.target_node_id

        # Determine workspace from target
        self.workspace = None
        if self.target_node_id:
            self.workspace = self.launch_profile_service.find_originating_workspace(
                self.target_node_id
            )

    def compose(self) -> ComposeResult:
        title_text = "Edit Launch Profile" if self.profile else "Create Launch Profile"

        # Load directories in this workspace as choices for working directory Select
        wd_choices = [("None (Preserves target default)", None)]
        if self.workspace:
            all_nodes = self.node_service.repository.list_all()
            for node in all_nodes:
                if node.node_kind == "resource" and node.resource_type == "directory":
                    # Check if node belongs to this workspace
                    node_ws = self.launch_profile_service.find_originating_workspace(
                        node.id
                    )
                    if node_ws and node_ws.id == self.workspace.id:
                        wd_choices.append((node.name, node.id))

        with Container(id="dialog-container"):
            yield Label(title_text, classes="title")

            with Vertical(classes="field-container"):
                yield Label("Profile Name *", classes="field-label")
                initial_name = ""
                if self.profile:
                    profile_node = self.node_service.get_node(
                        self.profile.profile_node_id
                    )
                    if profile_node:
                        initial_name = profile_node.name
                yield Input(
                    value=initial_name,
                    placeholder="Enter profile name...",
                    id="input-name",
                )

            with Vertical(classes="field-container"):
                yield Label("Arguments", classes="field-label")
                initial_args = ""
                if self.profile:
                    # Space-separated parsed safely via shlex
                    args_list = self.profile.argv
                    # Join safely preserving spaces or quotes if necessary
                    initial_args = " ".join(shlex.quote(a) for a in args_list)
                yield Input(
                    value=initial_args,
                    placeholder="e.g. run --port 8000",
                    id="input-arguments",
                )

            with Vertical(classes="field-container"):
                yield Label("Working Directory", classes="field-label")
                initial_wd = None
                if self.profile and any(
                    choice[1] == self.profile.working_directory_node_id
                    for choice in wd_choices
                ):
                    initial_wd = self.profile.working_directory_node_id
                yield Select(
                    wd_choices,
                    value=initial_wd,
                    allow_blank=True,
                    id="select-wd",
                )

            with Vertical(classes="field-container"):
                yield Label("Terminal Mode", classes="field-label")
                with RadioSet(id="terminal-mode-radio-set"):
                    is_inherit = True
                    is_new = False
                    if self.profile and self.profile.terminal_mode == "new_terminal":
                        is_inherit = False
                        is_new = True
                    yield RadioButton("Inherit", value=is_inherit, id="radio-inherit")
                    yield RadioButton(
                        "New Terminal", value=is_new, id="radio-new-terminal"
                    )

            yield Static("", id="status-area")

            with Horizontal(classes="buttons-container"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button(
                    "Save" if self.profile else "Create",
                    variant="primary",
                    id="btn-save",
                )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-save":
            self.action_submit()

    def action_submit(self) -> None:
        status_area = self.query_one("#status-area", Static)
        status_area.update("")

        name = self.query_one("#input-name", Input).value.strip()
        if not name:
            status_area.update("Profile Name is required.")
            return

        arguments_str = self.query_one("#input-arguments", Input).value.strip()
        try:
            arguments = shlex.split(arguments_str) if arguments_str else []
        except ValueError as e:
            status_area.update(f"Failed to parse arguments: {e}")
            return

        wd_val = self.query_one("#select-wd", Select).value
        wd_id = resolve_optional_uuid(wd_val)

        radio_set = self.query_one("#terminal-mode-radio-set", RadioSet)
        terminal_mode = "inherit"
        if radio_set.pressed_index == 1:
            terminal_mode = "new_terminal"

        try:
            if self.profile:
                # Update
                self.launch_profile_service.update_profile(
                    self.profile.id,
                    name=name,
                    arguments=arguments,
                    working_directory_node_id=wd_id,
                    clear_working_directory=(wd_id is None),
                    terminal_mode=terminal_mode,
                )
            else:
                # Create
                if not self.target_node_id:
                    status_area.update("Missing target node ID.")
                    return
                self.launch_profile_service.create_profile(
                    name=name,
                    target_node_id=self.target_node_id,
                    arguments=arguments,
                    working_directory_node_id=wd_id,
                    terminal_mode=terminal_mode,
                )
            self.dismiss(True)
        except LaunchProfileServiceError as e:
            status_area.update(str(e))

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.dismiss(False)
        elif event.key == "enter":
            focused = self.screen.focused
            submit_ids = {
                "btn-save",
                "input-name",
                "input-arguments",
            }
            cancel_ids = {
                "btn-cancel",
            }
            if focused and focused.id in submit_ids:
                event.prevent_default()
                event.stop()
                self.action_submit()
            elif focused and focused.id in cancel_ids:
                event.prevent_default()
                event.stop()
                self.dismiss(False)
