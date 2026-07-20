import os
import uuid

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Select,
    Static,
)

from pathtree.services.node_service import NodeService, NodeServiceError
from pathtree.ui.compat import resolve_optional_uuid


class AddNodeDialog(ModalScreen[uuid.UUID | None]):
    """Dialog for creating a new node (Workspace, Folder, or Directory)."""

    CSS = """
    AddNodeDialog {
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

    #warning-area {
        height: 2;
        margin-top: 0;
        color: $warning;
        text-style: italic;
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
        default_parent_id: uuid.UUID | None = None,
    ) -> None:
        super().__init__()
        self.node_service = node_service
        self.default_parent_id = default_parent_id
        # We start with workspace selected by default
        self.selected_type = "workspace"

    def compose(self) -> ComposeResult:
        parent_choices = self.node_service.get_parent_choices()

        with Container(id="dialog-container"):
            yield Label("Add New Node", classes="title")

            with Vertical(classes="field-container"):
                yield Label("Node Type", classes="field-label")
                with RadioSet(id="node-type-radio-set"):
                    yield RadioButton("Workspace", value=True, id="radio-workspace")
                    yield RadioButton("Folder", id="radio-folder")
                    yield RadioButton("Directory", id="radio-directory")

            with Vertical(classes="field-container"):
                yield Label("Name *", classes="field-label")
                yield Input(placeholder="Enter name...", id="input-name")

            with Vertical(classes="field-container", id="path-field-container"):
                yield Label("Path", classes="field-label")
                yield Input(placeholder="Enter path (optional)...", id="input-path")

            with Vertical(classes="field-container"):
                yield Label("Description", classes="field-label")
                yield Input(
                    placeholder="Enter description (optional)...",
                    id="input-description",
                )

            with Vertical(classes="field-container"):
                yield Label("Icon", classes="field-label")
                yield Input(placeholder="Enter icon (optional)...", id="input-icon")

            with Vertical(classes="field-container", id="parent-field-container"):
                yield Label("Parent", classes="field-label")
                yield Select(
                    parent_choices,
                    value=self.default_parent_id,
                    allow_blank=False,
                    id="select-parent",
                )

            with Horizontal(classes="field-container"):
                yield Checkbox("Favorite", value=False, id="checkbox-favorite")
                yield Checkbox("Temporary", value=False, id="checkbox-temporary")

            yield Static("", id="warning-area")
            yield Static("", id="status-area")

            with Horizontal(classes="buttons-container"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Create", variant="primary", id="btn-create")

    def on_mount(self) -> None:
        self.update_parent_choices()

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        radio_id = event.pressed.id
        if radio_id == "radio-workspace":
            self.selected_type = "workspace"
        elif radio_id == "radio-folder":
            self.selected_type = "folder"
        elif radio_id == "radio-directory":
            self.selected_type = "directory"
        self.update_parent_choices()

    def update_parent_choices(self) -> None:
        """Update parent choices in the select dropdown based on chosen type."""
        path_container = self.query_one("#path-field-container", Vertical)
        temp_checkbox = self.query_one("#checkbox-temporary", Checkbox)
        parent_container = self.query_one("#parent-field-container", Vertical)
        select_parent = self.query_one("#select-parent", Select)
        warning_area = self.query_one("#warning-area", Static)

        create_btn = self.query_one("#btn-create", Button)

        if self.selected_type == "workspace":
            path_container.display = False
            temp_checkbox.display = False
            parent_container.display = False
            select_parent.disabled = True
            warning_area.update("")
            create_btn.disabled = False
            return

        # Folder or Directory:
        path_container.display = self.selected_type == "directory"
        temp_checkbox.display = self.selected_type == "directory"
        parent_container.display = True
        select_parent.disabled = False

        # Retrieve all parent choices from node service
        all_choices = self.node_service.get_parent_choices()
        # Filter choices: only Workspace and Folder nodes (excluding Root,
        # i.e. None value, and Directory resources)
        valid_choices = []
        for label, val_id in all_choices:
            if val_id is not None:
                parent_node = self.node_service.get_node(val_id)
                if parent_node is not None and parent_node.node_kind in (
                    "workspace",
                    "folder",
                ):
                    valid_choices.append((label, val_id))

        if not valid_choices:
            select_parent.disabled = True
            create_btn.disabled = True
            warning_area.update(
                f"No valid parent Workspaces or Folders available to create a "
                f"{self.selected_type.capitalize()}. Please create a Workspace first."
            )
            return

        select_parent.set_options(valid_choices)
        create_btn.disabled = False
        warning_area.update("")

        # Derives the default parent only when valid for chosen type
        valid = False
        if self.default_parent_id is not None:
            parent_node = self.node_service.get_node(self.default_parent_id)
            if parent_node is not None and parent_node.node_kind in (
                "workspace",
                "folder",
            ):
                valid = True

        if valid:
            select_parent.value = self.default_parent_id
        else:
            select_parent.value = valid_choices[0][1]

    def on_input_changed(self, event: Input.Changed) -> None:
        # We handle real-time path validation warning for Directory path
        if event.input.id == "input-path" and self.selected_type == "directory":
            path_val = event.value.strip()
            warning_area = self.query_one("#warning-area", Static)
            if path_val and not os.path.exists(os.path.expanduser(path_val)):
                warning_area.update(
                    "Path does not currently exist. The entry will still be saved."
                )
            else:
                warning_area.update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-create":
            self.action_submit()

    def action_submit(self) -> None:
        status_area = self.query_one("#status-area", Static)
        status_area.update("")

        name = self.query_one("#input-name", Input).value
        description = self.query_one("#input-description", Input).value or None
        icon = self.query_one("#input-icon", Input).value or None

        parent_val = self.query_one("#select-parent", Select).value
        parent_id = resolve_optional_uuid(parent_val)

        is_favorite = self.query_one("#checkbox-favorite", Checkbox).value

        if self.selected_type == "workspace":
            node_kind = "workspace"
            resource_type = None
            path = None
            is_temporary = False
            parent_id = None  # Always force Workspace to be at root (None)
        elif self.selected_type == "folder":
            if parent_id is None:
                status_area.update("A valid parent Workspace or Folder is required.")
                return
            node_kind = "folder"
            resource_type = None
            path = None
            is_temporary = False
        else:  # directory
            if parent_id is None:
                status_area.update("A valid parent Workspace or Folder is required.")
                return
            node_kind = "resource"
            resource_type = "directory"
            path = self.query_one("#input-path", Input).value or None
            is_temporary = self.query_one("#checkbox-temporary", Checkbox).value

        try:
            new_node = self.node_service.create_node(
                name=name,
                node_kind=node_kind,
                resource_type=resource_type,
                parent_id=parent_id,
                path=path,
                description=description,
                icon=icon,
                is_favorite=is_favorite,
                is_temporary=is_temporary,
            )
            self.dismiss(new_node.id)
        except NodeServiceError as e:
            status_area.update(str(e))

    def action_cancel(self) -> None:
        self.dismiss(None)

    # Key bindings inside dialog
    def on_key(self, event) -> None:
        if event.key == "escape":
            event.prevent_default()
            self.dismiss(None)
        elif event.key == "enter":
            # Only submit if a button/input has focus, otherwise normal Textual behavior
            focused = self.screen.focused
            target_ids = {
                "btn-create",
                "input-name",
                "input-path",
                "input-description",
                "input-icon",
            }
            if focused and focused.id in target_ids:
                event.prevent_default()
                self.action_submit()
