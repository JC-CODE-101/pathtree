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


class PathAutocompleteOptionList(OptionList):
    """Custom OptionList routing selections back to its parent."""

    def __init__(
        self, *args, parent_widget: "PathAutocomplete" = None, **kwargs
    ) -> None:
        """Initialize with a reference to the parent PathAutocomplete widget."""
        super().__init__(*args, **kwargs)
        self.parent_widget = parent_widget

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Forward option selection to the parent PathAutocomplete widget."""
        if self.parent_widget and not event.option.disabled:
            self.parent_widget.accept_suggestion(str(event.option.prompt))


class PathAutocomplete(Widget):
    """A reusable path autocomplete widget with directory suggestions."""

    CSS: ClassVar[str] = """
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
        self.option_list = PathAutocompleteOptionList(
            classes="path-suggestions-list", parent_widget=self
        )

    def compose(self) -> ComposeResult:
        """Compose the wrapped Input and suggestions OptionList."""
        yield PathAutocompleteInput(
            value=self.initial_value,
            placeholder=self.placeholder,
            id=self.input_id,
            classes="path-autocomplete-input",
        )

    def on_mount(self) -> None:
        """Mount the OptionList dynamically to the dialog container or screen."""
        try:
            container = self.screen.query_one("#dialog-container")
            container.mount(self.option_list)
        except Exception:
            self.screen.mount(self.option_list)
        self.hide_suggestions()

    def on_unmount(self) -> None:
        """Clean up by removing the OptionList from its parent."""
        if self.option_list.parent:
            self.option_list.remove()

    def update_suggestions_position(self) -> None:
        """Position the OptionList overlay directly below the input field."""
        try:
            input_widget = self.query_one(f"#{self.input_id}", Input)
            parent = self.option_list.parent
            if parent is None:
                return

            # Both regions are screen-relative in Textual
            input_reg = input_widget.region
            parent_reg = parent.region

            x = input_reg.x - parent_reg.x
            y = (input_reg.y - parent_reg.y) + input_reg.height

            self.option_list.styles.position = "absolute"
            self.option_list.styles.offset = (x, y)
            if input_reg.width > 0:
                self.option_list.styles.width = input_reg.width
            else:
                self.option_list.styles.width = "100%"
        except Exception:
            pass

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
        self.update_suggestions_position()
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
