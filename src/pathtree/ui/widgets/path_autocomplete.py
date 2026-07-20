"""Reusable PathAutocomplete widget for Directory path inputs."""

import os
from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option


class PathAutocompleteInput(Input):
    """Custom Input subclass that allows key interception by parent PathAutocomplete."""

    def on_key(self, event: events.Key) -> None:
        """Forward keys to parent PathAutocomplete for interception."""
        if self.parent and hasattr(self.parent, "handle_input_key"):
            if self.parent.handle_input_key(event):
                event.prevent_default()
                event.stop()

    def on_blur(self, event: events.Blur) -> None:
        """Hide suggestions when focus leaves the input."""
        if self.parent and hasattr(self.parent, "hide_suggestions"):
            self.parent.hide_suggestions()


class PathAutocomplete(Widget):
    """A reusable path autocomplete widget with directory suggestions."""

    CSS: ClassVar[str] = """
    PathAutocomplete {
        height: auto;
        layout: vertical;
        position: relative;
    }

    PathAutocomplete .path-suggestions-list {
        display: none;
        position: absolute;
        top: 3;
        left: 0;
        width: 100%;
        max-height: 8;
        z-index: 1000;
        background: $panel;
        border: thin $accent;
    }
    """

    def __init__(
        self,
        value: str = "",
        placeholder: str = "",
        id: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize PathAutocomplete with wrapped Input configurations."""
        # Use a separate ID for the wrapper to avoid duplicate ID conflicts
        wrapper_id = f"{id}-wrapper" if id else None
        super().__init__(id=wrapper_id, **kwargs)
        self.initial_value = value
        self.placeholder = placeholder
        self.input_id = id or "input-path"
        self.is_suggestions_visible = False
        self._last_accepted_value = None
        self.option_list = OptionList(classes="path-suggestions-list")

    def compose(self) -> ComposeResult:
        """Compose the wrapped Input and suggestions OptionList."""
        yield PathAutocompleteInput(
            value=self.initial_value,
            placeholder=self.placeholder,
            id=self.input_id,
        )
        yield self.option_list

    def on_mount(self) -> None:
        """Initialize the suggestion list state."""
        self.hide_suggestions()

    def handle_input_key(self, event: events.Key) -> bool:
        """Handle key interception from the inner Input widget.

        Returns:
            True if the key was handled and should be intercepted; False otherwise.
        """
        if not self.is_suggestions_visible:
            return False

        key = event.key
        if key in ("down", "ctrl+n"):
            self.move_highlight(1)
            return True
        elif key in ("up", "ctrl+p"):
            self.move_highlight(-1)
            return True
        elif key == "tab":
            self.accept_highlighted_suggestion()
            return True
        elif key == "enter":
            if self.has_valid_suggestion_highlighted():
                self.accept_highlighted_suggestion()
                return True
            else:
                self.hide_suggestions()
                return False  # Do NOT consume Enter. Let dialog process it.
        elif key == "escape":
            self.hide_suggestions()
            return True

        return False

    def move_highlight(self, direction: int) -> None:
        """Move the highlighted suggestion in the specified direction.

        Wraps around when reaching boundaries.
        """
        count = self.option_list.option_count
        if count == 0:
            return

        current = self.option_list.highlighted
        if current is None:
            new_idx = 0 if direction > 0 else count - 1
        else:
            new_idx = (current + direction) % count

        # If option is disabled, try to find a non-disabled one
        start_idx = new_idx
        while self.option_list.get_option_at_index(new_idx).disabled:
            new_idx = (new_idx + direction) % count
            if new_idx == start_idx:
                break

        self.option_list.highlighted = new_idx

    def has_valid_suggestion_highlighted(self) -> bool:
        """Check if a valid (non-disabled) suggestion is highlighted."""
        current = self.option_list.highlighted
        if current is None:
            return False
        option = self.option_list.get_option_at_index(current)
        return not option.disabled

    def accept_suggestion(self, suggestion: str) -> None:
        """Accept a suggestion string and update the input value."""
        input_widget = self.query_one(f"#{self.input_id}", Input)
        current_value = input_widget.value

        last_slash_idx = current_value.rfind("/")
        if last_slash_idx != -1:
            new_value = current_value[: last_slash_idx + 1] + suggestion
        else:
            new_value = suggestion

        self._last_accepted_value = new_value
        input_widget.value = new_value
        input_widget.cursor_position = len(new_value)

        self.hide_suggestions()

    def accept_highlighted_suggestion(self) -> None:
        """Accept the highlighted suggestion and update the input value."""
        if not self.has_valid_suggestion_highlighted():
            return

        current = self.option_list.highlighted
        if current is None:
            return
        option = self.option_list.get_option_at_index(current)
        self.accept_suggestion(str(option.prompt))

    def show_suggestions(self) -> None:
        """Display the suggestion list overlay."""
        self.option_list.display = True
        self.is_suggestions_visible = True

    def hide_suggestions(self) -> None:
        """Hide the suggestion list overlay."""
        self.option_list.display = False
        self.is_suggestions_visible = False

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle real-time suggestions updates as the user types."""
        if event.input.id != self.input_id:
            return

        value = event.value
        if self._last_accepted_value == value:
            return

        self._last_accepted_value = None

        if not value.strip():
            self.hide_suggestions()
            return

        self.update_suggestions(value)

    def on_blur(self, event: events.Blur) -> None:
        """Hide suggestions when focus leaves the widget."""
        self.hide_suggestions()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle mouse clicks on suggestion items."""
        if not event.option.disabled:
            self.accept_suggestion(str(event.option.prompt))

    def update_suggestions(self, value: str) -> None:
        """Scan parent directory and update the suggestions list."""
        last_slash_idx = value.rfind("/")
        if last_slash_idx != -1:
            typed_dir = value[: last_slash_idx + 1]
            typed_prefix = value[last_slash_idx + 1 :]
        else:
            typed_dir = ""
            typed_prefix = value

        scandir_path = os.path.expanduser(typed_dir) if typed_dir else "."

        # 1. Validate parent directory existence and directory status
        if not os.path.exists(scandir_path):
            self.option_list.clear_options()
            self.option_list.add_option(
                Option("Directory does not exist.", disabled=True)
            )
            self.show_suggestions()
            return

        if not os.path.isdir(scandir_path):
            self.option_list.clear_options()
            self.option_list.add_option(
                Option("Directory is not accessible.", disabled=True)
            )
            self.show_suggestions()
            return

        # 2. Scan parent directory (non-recursive, directories only)
        entries = []
        try:
            with os.scandir(scandir_path) as it:
                while True:
                    try:
                        entry = next(it, None)
                        if entry is None:
                            break
                        try:
                            if entry.is_dir(follow_symlinks=True):
                                entries.append(entry.name + "/")
                        except OSError:
                            # Safely ignore a single broken entry
                            pass
                    except OSError as e:
                        # Re-raise directory scan failure so outer try-except catches it
                        raise e
        except PermissionError:
            self.option_list.clear_options()
            self.option_list.add_option(Option("Permission denied.", disabled=True))
            self.show_suggestions()
            return
        except OSError:
            self.option_list.clear_options()
            self.option_list.add_option(
                Option("Directory is not accessible.", disabled=True)
            )
            self.show_suggestions()
            return

        # Sort names alphabetically
        entries.sort()

        # 3. Add special dot/dot-dot directories matching the prefix
        special_dirs = []
        if typed_prefix == ".":
            special_dirs = ["./", "../"]
        elif typed_prefix == "..":
            special_dirs = ["../"]

        # Filter standard directories by prefix
        matches = [name for name in entries if name.startswith(typed_prefix)]

        # Combine, preserving uniqueness and order
        all_matches = []
        seen = set()
        for name in special_dirs + matches:
            if name not in seen:
                seen.add(name)
                all_matches.append(name)

        # 4. Display options
        self.option_list.clear_options()
        if not all_matches:
            self.option_list.add_option(
                Option("No matching directories.", disabled=True)
            )
            self.show_suggestions()
            return

        for match in all_matches:
            self.option_list.add_option(Option(match))

        self.option_list.highlighted = 0
        self.show_suggestions()
