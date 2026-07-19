"""Search input widget for filtering nodes."""

from typing import ClassVar

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Input


class SearchInput(Input):
    """A search input widget with custom navigation keybindings."""

    BINDINGS: ClassVar[list[Binding]] = [
        Binding("escape", "escape_pressed", "Clear & Exit Search", show=False),
        Binding("down", "down_pressed", "Focus Tree", show=False),
        Binding("enter", "enter_pressed", "Submit Search", show=False),
    ]

    class EscapePressed(Message):
        """Sent when Escape is pressed inside the search input."""

    class DownPressed(Message):
        """Sent when Down is pressed inside the search input."""

    class EnterPressed(Message):
        """Sent when Enter is pressed inside the search input."""

    def __init__(self, **kwargs) -> None:
        """Initialize SearchInput with the standard placeholder."""
        kwargs.setdefault(
            "placeholder",
            "Search nodes or use type:workspace, type:folder, type:directory",
        )
        super().__init__(**kwargs)

    def action_escape_pressed(self) -> None:
        """Handle escape key press."""
        self.post_message(self.EscapePressed())

    def action_down_pressed(self) -> None:
        """Handle down key press."""
        self.post_message(self.DownPressed())

    def action_enter_pressed(self) -> None:
        """Handle enter key press."""
        self.post_message(self.EnterPressed())
