import uuid
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Static

from pathtree.services.node_service import NodeService, NodeServiceError


@dataclass
class DeleteResult:
    """Result returned by ConfirmDeleteDialog."""

    deleted: bool
    descendant_count: int


class ConfirmDeleteDialog(ModalScreen[DeleteResult]):
    """Dialog for confirming deletion of a node.

    Displays descendant counts recursively.
    """

    CSS = """
    ConfirmDeleteDialog {
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

    .message {
        margin-bottom: 1;
        text-align: center;
    }

    .warning {
        color: $error;
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }

    #status-area {
        height: 2;
        color: $error;
        text-style: bold;
    }

    .buttons-container {
        align: center middle;
        margin-top: 1;
        height: auto;
    }

    Button {
        margin-left: 2;
    }
    """

    def __init__(self, node_service: NodeService, node_id: uuid.UUID) -> None:
        super().__init__()
        self.node_service = node_service
        self.node_id = node_id
        self.node = self.node_service.get_node(node_id)
        if self.node is None:
            raise ValueError(f"Node {node_id} not found.")

        try:
            self.descendant_count = self.node_service.count_descendants(node_id)
        except NodeServiceError:
            self.descendant_count = 0

    def compose(self) -> ComposeResult:
        with Container(id="dialog-container"):
            yield Label(f'Delete "{self.node.name}"?', classes="title")

            node_type = (
                self.node.resource_type
                if self.node.resource_type
                else self.node.node_kind
            )
            desc_text = (
                "This node has no descendants."
                if self.descendant_count == 0
                else f"This will also delete {self.descendant_count} descendants."
            )

            yield Label(f"Type: {node_type}", classes="message")
            yield Label(desc_text, classes="message")
            yield Label(
                "Are you sure? Recursive deletion is permanent.",
                classes="warning",
            )

            yield Static("", id="status-area")

            with Horizontal(classes="buttons-container"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Delete", variant="error", id="btn-delete")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(DeleteResult(deleted=False, descendant_count=0))
        elif event.button.id == "btn-delete":
            self.action_submit()

    def action_submit(self) -> None:
        status_area = self.query_one("#status-area", Static)
        status_area.update("")

        try:
            self.node_service.delete_node(self.node_id, recursive=True)
            self.dismiss(
                DeleteResult(deleted=True, descendant_count=self.descendant_count)
            )
        except NodeServiceError as e:
            status_area.update(str(e))

    def action_cancel(self) -> None:
        self.dismiss(DeleteResult(deleted=False, descendant_count=0))

    # Key bindings inside dialog
    def on_key(self, event) -> None:
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.action_cancel()
        elif event.key == "enter":
            focused = self.screen.focused
            submit_ids = {
                "btn-delete",
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
