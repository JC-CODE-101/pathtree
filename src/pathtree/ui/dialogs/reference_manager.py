import uuid

from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static

from pathtree.models.node import Node
from pathtree.services.node_service import NodeService, ValidationError
from pathtree.services.resource_reference_service import ResourceReferenceService


class ReferenceManagerDialog(ModalScreen[bool]):
    """Unified Dialog for managing Resource References (create, copy, move, reconnect)."""

    CSS = """
    ReferenceManagerDialog {
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
        ref_service: ResourceReferenceService,
        original_node_id: uuid.UUID | None = None,
        reference_node_id: uuid.UUID | None = None,
        mode: str = "create",  # "create" | "copy" | "move" | "reconnect"
    ) -> None:
        super().__init__()
        self.node_service = node_service
        self.ref_service = ref_service
        self.original_node_id = original_node_id
        self.reference_node_id = reference_node_id
        self.mode = mode

        # Resolve starting names and values
        self.default_name = ""
        if self.mode == "create" and self.original_node_id:
            orig = self.node_service.get_node(self.original_node_id)
            if orig:
                self.default_name = orig.name
        elif self.mode in ("copy", "move", "reconnect") and self.reference_node_id:
            ref_node = self.node_service.get_node(self.reference_node_id)
            if ref_node:
                self.default_name = ref_node.name

    def get_workspaces(self) -> list[tuple[str, uuid.UUID]]:
        """Get all workspace nodes."""
        nodes = self.node_service.repository.list_all()
        return [(n.name, n.id) for n in nodes if n.node_kind == "workspace"]

    def get_custom_folders(
        self, workspace_id: uuid.UUID
    ) -> list[tuple[str, uuid.UUID]]:
        """Get Custom group and all recursive folders under Custom of a workspace."""
        from sqlmodel import select

        stmt = select(Node).where(
            Node.parent_id == workspace_id,
            Node.node_kind == "system_group",
            Node.system_role == "custom",
        )
        custom_group = self.node_service.repository.session.exec(stmt).first()
        if not custom_group:
            return []

        choices = [("Custom (Root)", custom_group.id)]

        descendants = self.node_service.repository.get_descendants(custom_group.id)
        folder_nodes = [d for d in descendants if d.node_kind == "folder"]

        def build_label(node: Node) -> str:
            path_parts = [node.name]
            curr = node
            while curr.parent_id is not None and curr.parent_id != custom_group.id:
                parent = self.node_service.get_node(curr.parent_id)
                if parent:
                    path_parts.insert(0, parent.name)
                    curr = parent
                else:
                    break
            return "Custom / " + " / ".join(path_parts)

        for folder in folder_nodes:
            choices.append((build_label(folder), folder.id))

        return choices

    def get_real_resources(self) -> list[tuple[str, uuid.UUID]]:
        """Get all real resource nodes (excluding references) grouped by hierarchy for reconnection."""
        nodes = self.node_service.repository.list_all()
        choices = []
        for n in nodes:
            if n.node_kind == "resource" and n.resource_type != "reference":
                # Build pretty hierarchical path
                parts = [n.name]
                curr = n
                while curr.parent_id is not None:
                    parent = self.node_service.get_node(curr.parent_id)
                    if parent:
                        parts.insert(0, parent.name)
                        curr = parent
                    else:
                        break
                choices.append((" / ".join(parts), n.id))
        return choices

    def compose(self) -> ComposeResult:
        title_map = {
            "create": "Create Resource Reference",
            "copy": "Copy Reference to Workspace",
            "move": "Move Reference to Workspace",
            "reconnect": "Reconnect Broken Reference",
        }

        with Container(id="dialog-container"):
            yield Label(title_map.get(self.mode, "Manage Reference"), classes="title")

            if self.mode == "reconnect":
                with Vertical(classes="field-container"):
                    yield Label("Select New Original Resource", classes="field-label")
                    yield Select(self.get_real_resources(), id="select-original")
            else:
                # Workspace / Folder destination fields
                workspaces = self.get_workspaces()
                initial_ws_val = workspaces[0][1] if workspaces else None

                with Vertical(classes="field-container"):
                    yield Label("Destination Workspace", classes="field-label")
                    yield Select(
                        workspaces, value=initial_ws_val, id="select-workspace"
                    )

                initial_folders = (
                    self.get_custom_folders(initial_ws_val) if initial_ws_val else []
                )
                initial_folder_val = initial_folders[0][1] if initial_folders else None

                with Vertical(classes="field-container"):
                    yield Label("Destination Folder", classes="field-label")
                    yield Select(
                        initial_folders, value=initial_folder_val, id="select-folder"
                    )

                with Vertical(classes="field-container"):
                    yield Label("Reference Name", classes="field-label")
                    yield Input(
                        value=self.default_name,
                        placeholder="Enter name...",
                        id="input-name",
                    )

            yield Static("", id="status-area")

            with Horizontal(classes="buttons-container"):
                yield Button("Cancel", variant="default", id="btn-cancel")
                action_btn_label = {
                    "create": "Create",
                    "copy": "Copy",
                    "move": "Move",
                    "reconnect": "Reconnect",
                }.get(self.mode, "Submit")
                yield Button(action_btn_label, variant="primary", id="btn-submit")

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "select-workspace" and event.value is not None:
            # Update folder Select choices in real-time
            folder_select = self.query_one("#select-folder", Select)
            folders = self.get_custom_folders(event.value)
            folder_select.set_options(folders)
            if folders:
                folder_select.value = folders[0][1]
            else:
                folder_select.value = None

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(False)
        elif event.button.id == "btn-submit":
            self.action_submit()

    def action_submit(self) -> None:
        status_area = self.query_one("#status-area", Static)
        status_area.update("")

        if self.mode == "reconnect":
            original_val = self.query_one("#select-original", Select).value
            if not original_val:
                status_area.update("Please select a valid original resource.")
                return
            try:
                self.ref_service.reconnect_reference(
                    self.reference_node_id, original_val
                )
                self.app.notify("Reference reconnected successfully.")
                self.dismiss(True)
            except Exception as e:
                status_area.update(str(e))

        else:
            folder_val = self.query_one("#select-folder", Select).value
            if not folder_val:
                status_area.update("Please select a destination folder inside Custom.")
                return

            name_val = self.query_one("#input-name", Input).value.strip()
            if not name_val:
                status_area.update("Reference Name cannot be empty.")
                return

            if self.mode == "create":
                try:
                    self.ref_service.create_reference(
                        original_node_id=self.original_node_id,
                        destination_parent_id=folder_val,
                        custom_name=name_val,
                    )
                    self.app.notify(f"Created reference '{name_val}'")
                    self.dismiss(True)
                except Exception as e:
                    status_area.update(str(e))

            elif self.mode == "copy":
                try:
                    ref_rec = self.ref_service.get_reference_by_node_id(
                        self.reference_node_id
                    )
                    if not ref_rec:
                        raise ValidationError("Reference record not found.")

                    self.ref_service.create_reference(
                        original_node_id=ref_rec.original_node_id,
                        destination_parent_id=folder_val,
                        custom_name=name_val,
                    )
                    self.app.notify(f"Copied reference '{name_val}' successfully.")
                    self.dismiss(True)
                except Exception as e:
                    status_area.update(str(e))

            elif self.mode == "move":
                try:
                    # Move the reference node under the selected parent
                    self.node_service.move_node(self.reference_node_id, folder_val)
                    # Update reference name
                    self.node_service.update_node(self.reference_node_id, name=name_val)
                    self.app.notify(f"Moved reference '{name_val}' successfully.")
                    self.dismiss(True)
                except Exception as e:
                    status_area.update(str(e))

    def on_key(self, event) -> None:
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.dismiss(False)
        elif event.key == "enter":
            focused = self.screen.focused
            if focused and focused.id in (
                "btn-submit",
                "input-name",
                "select-folder",
                "select-workspace",
                "select-original",
            ):
                event.prevent_default()
                event.stop()
                self.action_submit()
            elif focused and focused.id == "btn-cancel":
                event.prevent_default()
                event.stop()
                self.dismiss(False)
            else:
                event.stop()
