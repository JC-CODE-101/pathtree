"""HistoryInput widget with Undo (Ctrl+Z) and selection collapse (Shift+E)."""

from typing import Any

from textual import events
from textual.widgets import Input


class HistoryInput(Input):
    """Input widget supporting undo history and selection collapse."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Initialize the input and set up state for tracking undo history."""
        super().__init__(*args, **kwargs)
        self._undo_history: list[tuple[str, tuple[int, int]]] = []
        self._is_undoing: bool = False
        self._last_value: str = self.value
        self._last_selection: tuple[int, int] = (
            self.selection.start,
            self.selection.end,
        )
        self._pre_key_state: tuple[str, tuple[int, int]] | None = None

    def watch_value(self, value: str) -> None:
        """React to changes in value, storing the previous state in history."""
        is_undoing = getattr(self, "_is_undoing", False)
        if not is_undoing:
            pre_key = getattr(self, "_pre_key_state", None)
            if pre_key is not None:
                old_val, old_sel = pre_key
            else:
                old_val = getattr(self, "_last_value", None)
                old_sel = getattr(
                    self,
                    "_last_selection",
                    (self.selection.start, self.selection.end),
                )

            if old_val is not None and value != old_val:
                if not hasattr(self, "_undo_history"):
                    self._undo_history = []
                self._undo_history.append((old_val, old_sel))

        self._last_value = value
        self._pre_key_state = None

    def watch_selection(self, selection: Any) -> None:
        """React to changes in selection, updating the last-known selection."""
        is_undoing = getattr(self, "_is_undoing", False)
        if not is_undoing:
            self._last_selection = (selection.start, selection.end)

    def on_key(self, event: events.Key) -> None:
        """Intercept key events to handle Ctrl+Z and Shift+E."""
        key = event.key
        aliases = getattr(event, "aliases", [])
        is_shift_e = key in ("E", "shift+e") or "shift+e" in aliases

        if key == "ctrl+z":
            event.prevent_default()
            event.stop()
            self.undo()
            return

        if is_shift_e:
            val_len = len(self.value)
            start, end = self.selection.start, self.selection.end
            if val_len > 0 and abs(start - end) == val_len:
                event.prevent_default()
                event.stop()
                self.cursor_position = val_len
                return

        # Record the current state before Textual handles the key event
        self._pre_key_state = (self.value, (self.selection.start, self.selection.end))

    def undo(self) -> None:
        """Restore the input to its previous state from the undo history."""
        if not getattr(self, "_undo_history", None):
            return

        prev_value, prev_selection = self._undo_history.pop()
        self._is_undoing = True
        try:
            self.value = prev_value
            self.selection = prev_selection
            self._last_value = prev_value
            self._last_selection = prev_selection
        finally:
            self._is_undoing = False
