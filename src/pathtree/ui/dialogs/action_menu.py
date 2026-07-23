"""Dialog for selecting an action to perform on a resource."""

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, Static

from pathtree.actions.base import ResourceAction


@dataclass
class ActionMenuResult:
    """Result returned by ResourceActionMenu."""

    action_id: str | None


class ActionMenuItem(Static):
    """A widget representing a single item in the resource action menu."""

    def __init__(self, action: ResourceAction, is_highlighted: bool = False) -> None:
        self.action = action
        self.is_highlighted = is_highlighted
        classes = "action-item"
        if not action.is_enabled:
            classes += " disabled"
        if is_highlighted:
            classes += " highlighted"
        super().__init__(classes=classes)

    def render(self) -> str:
        marker = "* " if self.action.is_default else "  "
        label = f"{marker}{self.action.label}"
        if not self.action.is_enabled:
            label += " (Disabled)"

        content = f"[bold]{label}[/bold]"
        if self.action.description:
            content += f"\n  [italic]{self.action.description}[/italic]"
        return content


class ResourceActionMenu(ModalScreen[ActionMenuResult]):
    """Modal dialog displaying a menu of actions for the selected resource."""

    CSS = """
    ResourceActionMenu {
        align: center middle;
        background: rgba(0, 0, 0, 0.5);
    }

    #menu-container {
        width: 60;
        height: auto;
        background: $panel;
        border: thick $accent;
        padding: 1 2;
    }

    .menu-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
        border-bottom: solid $accent;
        padding-bottom: 1;
    }

    .menu-items-list {
        height: auto;
    }

    .action-item {
        padding: 0 1;
        margin-bottom: 1;
        background: $surface;
        border: none;
        height: auto;
    }

    .action-item.highlighted {
        background: $accent;
        color: $text;
    }

    .action-item.disabled {
        color: $text-muted;
    }
    """

    def __init__(
        self, actions: list[ResourceAction], title: str = "Resource Actions"
    ) -> None:
        super().__init__()
        self.actions = actions
        self.title_text = title
        self.highlighted_index = 0

    def compose(self) -> ComposeResult:
        with Container(id="menu-container"):
            yield Label(self.title_text, classes="menu-title")
            with Vertical(classes="menu-items-list"):
                for idx, action in enumerate(self.actions):
                    yield ActionMenuItem(
                        action, is_highlighted=(idx == self.highlighted_index)
                    )

    def on_mount(self) -> None:
        self.update_highlighting()

    def select_next(self) -> None:
        if not self.actions:
            return
        self.highlighted_index = (self.highlighted_index + 1) % len(self.actions)
        self.update_highlighting()

    def select_prev(self) -> None:
        if not self.actions:
            return
        self.highlighted_index = (self.highlighted_index - 1) % len(self.actions)
        self.update_highlighting()

    def update_highlighting(self) -> None:
        items = self.query(ActionMenuItem)
        for idx, item in enumerate(items):
            item.set_class(idx == self.highlighted_index, "highlighted")
            if idx == self.highlighted_index:
                item.scroll_visible()

    def execute_highlighted(self) -> None:
        if 0 <= self.highlighted_index < len(self.actions):
            action = self.actions[self.highlighted_index]
            if action.is_enabled:
                self.dismiss(ActionMenuResult(action.id))

    def on_key(self, event) -> None:
        key = event.key.lower()
        if key == "escape":
            event.prevent_default()
            event.stop()
            self.dismiss(ActionMenuResult(None))
        elif key in ("j", "down", "ctrl+j"):
            event.prevent_default()
            event.stop()
            self.select_next()
        elif key in ("k", "up", "ctrl+k"):
            event.prevent_default()
            event.stop()
            self.select_prev()
        elif key == "enter":
            event.prevent_default()
            event.stop()
            self.execute_highlighted()
        else:
            # Consume other keys so they don't leak to the tree/main screen
            event.stop()
