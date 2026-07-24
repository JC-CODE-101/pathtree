import uuid
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import DataTable, Label

from pathtree.services.node_service import NodeService
from pathtree.services.pin_service import PinService


class PinsScreen(ModalScreen[uuid.UUID | None]):
    """Modal screen displaying global pinned resources.

    Supports wrapping navigation, reordering (via [ and ]),
    unpinning (via 'u' or 'delete'), and activation to locate/select the
    original node in the tree.
    """

    CSS = """
    PinsScreen {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #pins-container {
        width: 100;
        height: 30;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }

    .pins-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        border-bottom: solid $accent;
        padding-bottom: 1;
    }

    #pins-table {
        height: 1fr;
        border: none;
    }

    .pins-help {
        text-align: center;
        text-style: italic;
        color: $text-muted;
        margin-top: 1;
    }
    """

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "close_screen", "Close", show=True),
        Binding("enter", "activate_pin", "Go to Node", show=True),
        Binding("u", "unpin_selected", "Unpin", show=True),
        Binding("d", "unpin_selected", "Unpin", show=False),
        Binding("delete", "unpin_selected", "Unpin", show=False),
        Binding("[", "move_pin_up", "Move Up", show=True),
        Binding("]", "move_pin_down", "Move Down", show=True),
    ]

    def __init__(self, node_service: NodeService, pin_service: PinService) -> None:
        super().__init__()
        self.node_service = node_service
        self.pin_service = pin_service
        self._row_node_ids: list[uuid.UUID] = []

    def compose(self) -> ComposeResult:
        with Container(id="pins-container"):
            yield Label("Global Pinned Resources", classes="pins-title")
            yield DataTable(id="pins-table")
            yield Label(
                "[Enter] Go | [u] Unpin | [[] Up | []] Down | [Esc] Close",
                classes="pins-help",
            )

    def on_mount(self) -> None:
        table = self.query_one("#pins-table", DataTable)
        table.cursor_type = "row"
        table.add_column("Pos", width=4)
        table.add_column("Name/Label", width=25)
        table.add_column("Workspace", width=15)
        table.add_column("Type", width=12)
        table.add_column("Resolved Target", width=30)
        self.reload_pins()

    def _get_originating_workspace(self, node) -> str:
        """Resolve the workspace name of the node by climbing the tree."""
        curr = node
        while curr is not None:
            if curr.node_kind == "workspace":
                return curr.name
            if curr.parent_id is None:
                break
            curr = self.node_service.get_node(curr.parent_id)
        return "Root"

    def reload_pins(self, select_row_idx: int = 0) -> None:
        table = self.query_one("#pins-table", DataTable)
        table.clear()
        self._row_node_ids = []

        pins = self.pin_service.list_pins()
        for _idx, pin in enumerate(pins):
            node = self.node_service.get_node(pin.node_id)
            if node is None:
                # Skip stale reference in UI
                continue

            name = pin.custom_label or node.name
            workspace = self._get_originating_workspace(node)
            res_type = node.resource_type or node.node_kind
            target = node.path or ""

            table.add_row(
                str(pin.position),
                name,
                workspace,
                res_type,
                target,
            )
            self._row_node_ids.append(node.id)

        # Restore selection
        if self._row_node_ids:
            safe_row_idx = max(0, min(select_row_idx, len(self._row_node_ids) - 1))
            table.move_cursor(row=safe_row_idx)

    def action_close_screen(self) -> None:
        self.dismiss(None)

    def action_activate_pin(self) -> None:
        table = self.query_one("#pins-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self._row_node_ids):
            node_id = self._row_node_ids[cursor_row]
            self.dismiss(node_id)

    def action_unpin_selected(self) -> None:
        table = self.query_one("#pins-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and 0 <= cursor_row < len(self._row_node_ids):
            node_id = self._row_node_ids[cursor_row]
            self.pin_service.unpin_node(node_id)
            self.app.notify("Unpinned successfully")
            self.reload_pins(select_row_idx=cursor_row)

    def action_move_pin_up(self) -> None:
        table = self.query_one("#pins-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and cursor_row > 0:
            pins = self.pin_service.list_pins()
            current_pin = pins[cursor_row]
            new_pos = current_pin.position - 1
            self.pin_service.reorder_pin(current_pin.id, new_pos)
            self.reload_pins(select_row_idx=cursor_row - 1)

    def action_move_pin_down(self) -> None:
        table = self.query_one("#pins-table", DataTable)
        cursor_row = table.cursor_row
        if cursor_row is not None and cursor_row < len(self._row_node_ids) - 1:
            pins = self.pin_service.list_pins()
            current_pin = pins[cursor_row]
            new_pos = current_pin.position + 1
            self.pin_service.reorder_pin(current_pin.id, new_pos)
            self.reload_pins(select_row_idx=cursor_row + 1)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Trigger activation on enter / row select."""
        self.action_activate_pin()

    def on_key(self, event) -> None:
        # Prevent key leakage to parent screen
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self.action_close_screen()
        elif event.key == "enter":
            event.prevent_default()
            event.stop()
            self.action_activate_pin()
        elif event.key in ("u", "d", "delete", "[", "]"):
            # Stop keys from bubbling out
            event.stop()
