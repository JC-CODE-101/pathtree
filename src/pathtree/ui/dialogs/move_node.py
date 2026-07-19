import uuid

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, Static

from pathtree.services.node_service import NodeService, NodeServiceError


class MoveNodeDialog(ModalScreen[bool]):
    """Dialog for moving a node to a different parent."""

    CSS = """
    MoveNodeDialog {
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

    def __init__(self, node_service: NodeService, node_id: uuid.UUID) -> None:
        super().__init__()
        self.node_service = node_service
        self.node_id = node_id
        self.node = self.node_service.get_node(node_id)
        if self.node is None:
            raise ValueError(f"Node {node_id} not found.")

    def compose(self) -> ComposeResult:
        # Generate parent choices excluding self and descendants
        parent_choices = self.node_service.get_parent_choices(
            exclude_node_id=self.node_id
        )

        # Look up current parent label if exists
        current_parent_label = "Root"
        if self.node.parent_id is not None:
            parent_node = self.node_service.get_node(self.node.parent_id)
            if parent_node is not None:
                current_parent_label = parent_node.name

        with Container(id="dialog-container"):
            yield Label(f"Move Node: {self.node.name}", classes="title")

            with Vertical(classes="field-container"):
                yield Label(
                    f"Current Parent: {current_parent_label}",
                    classes="field-label",
                )

            with Vertical(classes="field-container"):
                yield Label("Select New Parent", classes="field-label")
                yield Select(
                    parent_choices,
                    value=self.node.parent_id,
                    allow_blank=True,
                    id="select-parent",
                )

            yield Static("", id="status-area")

            with Horizontal(classes="buttons-container"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Move", variant="primary", id="btn-move")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-move":
            self.action_submit()

    def action_submit(self) -> None:
        status_area = self.query_one("#status-area", Static)
        status_area.update("")

        parent_val = self.query_one("#select-parent", Select).value
        new_parent_id = parent_val if isinstance(parent_val, uuid.UUID) else None

        try:
            self.node_service.move_node(self.node_id, new_parent_id)
            self.dismiss(True)
        except NodeServiceError as e:
            status_area.update(str(e))

    def action_cancel(self) -> None:
        self.dismiss(False)

    # Key bindings inside dialog
    def on_key(self, event) -> None:
        if event.key == "escape":
            event.prevent_default()
            self.dismiss(False)
