import uuid

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Label, Select, Static

from pathtree.services.launch_profile_service import (
    LaunchProfileService,
    LaunchProfileServiceError,
)
from pathtree.services.node_service import NodeService
from pathtree.ui.compat import resolve_optional_uuid


class ReconnectTargetDialog(ModalScreen[bool]):
    """Dialog for reconnecting a detached Launch Profile to a compatible target."""

    CSS = """
    ReconnectTargetDialog {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #dialog-container {
        width: 65;
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

    .info-label {
        margin-bottom: 1;
        color: $warning;
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
        profile_id: uuid.UUID,
    ) -> None:
        super().__init__()
        self.node_service = node_service
        self.launch_profile_service = launch_profile_service
        self.profile_id = profile_id
        self.profile = self.launch_profile_service.get_profile(self.profile_id)

    def compose(self) -> ComposeResult:
        # Load compatible nodes as choices
        compat_choices = []
        all_nodes = self.node_service.repository.list_all()
        for node in all_nodes:
            if (
                node.node_kind == "resource"
                and node.resource_type == self.profile.target_resource_type
            ):
                ws = self.launch_profile_service.find_originating_workspace(node.id)
                ws_name = ws.name if ws else "None"
                label = f"[{ws_name}] {node.name} ({node.path or ''})"
                compat_choices.append((label, node.id))

        with Container(id="dialog-container"):
            yield Label("Reconnect Profile Target", classes="title")

            profile_node = self.node_service.get_node(self.profile.profile_node_id)
            profile_name = profile_node.name if profile_node else "Unknown"

            yield Label(
                f"Profile Name: {profile_name}\n"
                f"Expected Target Type: {self.profile.target_resource_type.upper()}",
                classes="info-label",
            )

            with Vertical(classes="field-container"):
                yield Label("Select New Target Node *", classes="field-label")
                yield Select(
                    compat_choices,
                    value=None,
                    allow_blank=True,
                    placeholder="Choose compatible target...",
                    id="select-target",
                )

            yield Static("", id="status-area")

            with Horizontal(classes="buttons-container"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                yield Button("Reconnect", variant="primary", id="btn-reconnect")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-reconnect":
            self.action_submit()

    def action_submit(self) -> None:
        status_area = self.query_one("#status-area", Static)
        status_area.update("")

        target_val = self.query_one("#select-target", Select).value
        target_id = resolve_optional_uuid(target_val)

        if not target_id:
            status_area.update("Please select a valid compatible target node.")
            return

        try:
            self.launch_profile_service.reconnect_profile(self.profile_id, target_id)
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
            if focused and focused.id in ("btn-reconnect", "select-target"):
                event.prevent_default()
                event.stop()
                self.action_submit()
            elif focused and focused.id == "btn-cancel":
                event.prevent_default()
                event.stop()
                self.dismiss(False)
