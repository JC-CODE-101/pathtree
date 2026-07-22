import os
import uuid

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static

from pathtree.services.node_service import NodeService, NodeServiceError
from pathtree.ui.widgets.history_input import HistoryInput
from pathtree.ui.widgets.icon_picker import IconPicker
from pathtree.ui.widgets.path_autocomplete import PathAutocomplete


class EditNodeDialog(ModalScreen[bool]):
    """Dialog for editing an existing node."""

    CSS = """
    EditNodeDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #dialog-container {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
        layers: base overlay;
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

    PathAutocomplete {
        width: 100%;
        height: 3;
        min-height: 3;
    }

    PathAutocomplete .path-autocomplete-input {
        width: 100%;
        height: 100%;
    }

    .path-suggestions-list {
        display: none;
        position: absolute;
        offset: 0 3;
        width: 100%;
        max-height: 8;
        background: $panel;
        border: solid $accent;
        layer: overlay;
    }
    """

    def __init__(self, node_service: NodeService, node_id: uuid.UUID) -> None:
        super().__init__()
        self.node_service = node_service
        self.node_id = node_id
        self.node = self.node_service.get_node(node_id)
        if self.node is None:
            raise ValueError(f"Node {node_id} not found.")

    def compose(self) -> ComposeResult:
        with Container(id="dialog-container"):
            yield Label(f"Edit Node: {self.node.name}", classes="title")

            with Vertical(classes="field-container"):
                yield Label("Name *", classes="field-label")
                yield HistoryInput(
                    value=self.node.name,
                    placeholder="Enter name...",
                    id="input-name",
                )

            # Show path only for directory resource
            is_directory = (
                self.node.node_kind == "resource"
                and self.node.resource_type == "directory"
            )
            with Vertical(classes="field-container", id="path-field-container") as vc:
                yield Label("Path", classes="field-label")
                yield PathAutocomplete(
                    value=self.node.path or "",
                    placeholder="Enter path...",
                    id="input-path",
                )
                if not is_directory:
                    vc.display = False

            with Vertical(classes="field-container"):
                yield Label("Description", classes="field-label")
                yield HistoryInput(
                    value=self.node.description or "",
                    placeholder="Enter description...",
                    id="input-description",
                )

            # Resolve current icon or default fallback if None
            from pathtree.utils.icons import NodeIconCatalog

            catalog = NodeIconCatalog()
            current_icon = self.node.icon
            if not current_icon:
                current_icon = catalog.get_default_icon(
                    self.node.node_kind, self.node.resource_type
                )

            with Vertical(classes="field-container"):
                yield Label("Icon", classes="field-label")
                yield IconPicker(
                    value=current_icon,
                    placeholder="Enter icon...",
                    id="input-icon",
                    node_kind=self.node.node_kind,
                    resource_type=self.node.resource_type,
                )

            with Vertical(classes="field-container"):
                yield Label("Sort Order", classes="field-label")
                yield HistoryInput(
                    value=str(self.node.sort_order),
                    placeholder="0",
                    id="input-sort-order",
                )

            with Horizontal(classes="field-container"):
                yield Checkbox(
                    "Favorite", value=self.node.is_favorite, id="checkbox-favorite"
                )

                # Show temporary checkbox. Toggling from temporary (True) to
                # permanent (False) is promotion. Permanent nodes
                # (is_temporary=False) cannot be demoted, so if node is already
                # permanent, disable/hide.
                cb_temp = Checkbox(
                    "Temporary", value=self.node.is_temporary, id="checkbox-temporary"
                )
                if not self.node.is_temporary:
                    cb_temp.display = False
                yield cb_temp

            yield Static("", id="warning-area")
            yield Static("", id="status-area")

            with Horizontal(classes="buttons-container"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Save", variant="primary", id="btn-save")

    def on_input_changed(self, event: Input.Changed) -> None:
        is_directory = (
            self.node.node_kind == "resource" and self.node.resource_type == "directory"
        )
        if event.input.id == "input-path" and is_directory:
            path_val = event.value.strip()
            warning_area = self.query_one("#warning-area", Static)
            if path_val:
                from pathtree.utils.path import normalize_path

                normalized = normalize_path(path_val)
                if not os.path.exists(normalized):
                    warning_area.update(
                        "Path does not currently exist. The entry will still be saved."
                    )
                else:
                    warning_area.update("")
            else:
                warning_area.update("")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-save":
            self.action_submit()

    def action_submit(self) -> None:
        status_area = self.query_one("#status-area", Static)
        status_area.update("")

        name = self.query_one("#input-name", Input).value
        description = self.query_one("#input-description", Input).value or None
        icon = self.query_one(IconPicker).value or None

        sort_order_str = self.query_one("#input-sort-order", Input).value
        try:
            sort_order = int(sort_order_str)
        except ValueError:
            status_area.update("Sort order must be an integer.")
            return

        is_favorite = self.query_one("#checkbox-favorite", Checkbox).value

        # Path is only saved/sent for Directory resources
        is_directory = (
            self.node.node_kind == "resource" and self.node.resource_type == "directory"
        )
        path = None
        if is_directory:
            path_val = self.query_one("#input-path", Input).value or None
            if path_val is not None:
                from pathtree.utils.path import normalize_path

                path = normalize_path(path_val)

        # Determine temporary promotion
        kwargs = {
            "name": name,
            "description": description,
            "icon": icon,
            "sort_order": sort_order,
            "is_favorite": is_favorite,
        }
        if is_directory:
            kwargs["path"] = path

        # If temporary checkbox was displayed and got toggled to False, we're promoting
        if self.node.is_temporary:
            is_temp_val = self.query_one("#checkbox-temporary", Checkbox).value
            kwargs["is_temporary"] = is_temp_val

        try:
            self.node_service.update_node(self.node_id, **kwargs)
            self.dismiss(True)
        except NodeServiceError as e:
            status_area.update(str(e))

    def action_cancel(self) -> None:
        self.dismiss(False)

    # Key bindings inside dialog
    def on_key(self, event) -> None:
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.action_cancel()
        elif event.key == "enter":
            focused = self.screen.focused
            submit_ids = {
                "btn-save",
                "input-name",
                "input-path",
                "input-description",
                "input-icon",
                "input-icon-input",
                "input-sort-order",
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
                self.action_cancel()
            else:
                event.stop()
