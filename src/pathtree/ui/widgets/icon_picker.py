"""A reusable, keyboard-friendly IconPicker widget for node dialogs."""

from typing import ClassVar

from textual import events
from textual.app import ComposeResult
from textual.css.query import NoMatches
from textual.widget import Widget
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

from pathtree.ui.widgets.history_input import HistoryInput
from pathtree.utils.icons import NodeIconCatalog


class IconPickerInput(HistoryInput):
    """Custom Input subclass for IconPicker."""

    def on_key(self, event: events.Key) -> None:
        """Forward keys to parent IconPicker for interception."""
        if self.parent and hasattr(self.parent, "handle_input_key"):
            if self.parent.handle_input_key(event):
                event.prevent_default()
                event.stop()
                return

        super().on_key(event)

    def on_blur(self, event: events.Blur) -> None:
        """Forward blur event to parent IconPicker for deferred handling."""
        if self.parent and hasattr(self.parent, "on_blur"):
            self.parent.on_blur(event)

    def on_focus(self, event: events.Focus) -> None:
        """Trigger populating and showing options when gaining focus."""
        if self.parent and hasattr(self.parent, "show_suggestions"):
            self.parent.show_suggestions()


class IconPickerOption(Option):
    """A custom option representing a selectable icon item."""

    def __init__(
        self,
        prompt: str,
        symbol: str,
        is_default: bool = False,
        is_custom: bool = False,
        **kwargs,
    ) -> None:
        """Initialize with symbol meta-information."""
        super().__init__(prompt, **kwargs)
        self.symbol = symbol
        self.is_default = is_default
        self.is_custom = is_custom


class IconPickerOptionList(OptionList):
    """Custom OptionList routing selections and focus back to parent IconPicker."""

    def __init__(self, *args, parent_widget: "IconPicker" = None, **kwargs) -> None:
        """Initialize with a reference to the parent IconPicker widget."""
        super().__init__(*args, **kwargs)
        self.parent_widget = parent_widget

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Forward option selection to the parent IconPicker widget."""
        if self.parent_widget and isinstance(event.option, IconPickerOption):
            self.parent_widget.accept_highlighted_option(event.option)

    def on_blur(self, event: events.Blur) -> None:
        """Forward blur event to parent IconPicker for deferred handling."""
        if self.parent_widget and hasattr(self.parent_widget, "on_blur"):
            self.parent_widget.on_blur(event)


class IconPicker(Widget):
    """A reusable icon picker with recommended unicode symbols."""

    CSS: ClassVar[str] = """
    IconPicker {
        width: 100%;
        height: 3;
        min-height: 3;
    }

    IconPicker .icon-picker-input {
        width: 100%;
        height: 100%;
    }

    .icon-suggestions-list {
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
        node_kind: str = "workspace",
        resource_type: str | None = None,
        **kwargs,
    ) -> None:
        """Initialize IconPicker with wrapper and wrapped Input config."""
        wrapper_id = f"{id}-wrapper" if id else None
        super().__init__(id=wrapper_id, **kwargs)
        self.placeholder = placeholder
        self.input_id = id or "input-icon"
        self.node_kind = node_kind
        self.resource_type = resource_type
        self.is_suggestions_visible = False
        self._is_accepting_option = False

        self.catalog = NodeIconCatalog()
        self.option_list = IconPickerOptionList(
            classes="icon-suggestions-list", parent_widget=self
        )

        if not value:
            value = self.catalog.get_default_icon(node_kind, resource_type)
        self.initial_value = value

    @property
    def value(self) -> str:
        """Get the current string value of the input."""
        try:
            input_widget = self.query_one(f"#{self.input_id}", Input)
            return input_widget.value
        except NoMatches:
            return self.initial_value

    @value.setter
    def value(self, val: str) -> None:
        """Set the current string value of the input."""
        self.initial_value = val
        try:
            input_widget = self.query_one(f"#{self.input_id}", Input)
            input_widget.value = val
        except NoMatches:
            pass

    def compose(self) -> ComposeResult:
        """Compose the wrapped Input."""
        yield IconPickerInput(
            value=self.initial_value,
            placeholder=self.placeholder,
            id=self.input_id,
            classes="icon-picker-input",
        )

    def on_mount(self) -> None:
        """Mount the OptionList dynamically to the dialog container or screen."""
        try:
            container = self.screen.query_one("#dialog-container")
            container.mount(self.option_list)
        except NoMatches:
            self.screen.mount(self.option_list)
        self.populate_options()
        self.hide_suggestions()

    def on_unmount(self) -> None:
        """Clean up by removing the OptionList from its parent."""
        if self.option_list.parent:
            self.option_list.remove()

    def populate_options(self) -> None:
        """Clear and re-populate recommended icon options based on current node type."""
        self.option_list.clear_options()

        # 1. Default Option
        default_symbol = self.catalog.get_default_icon(
            self.node_kind, self.resource_type
        )
        self.option_list.add_option(
            IconPickerOption(
                prompt=f"Default: {default_symbol}",
                symbol=default_symbol,
                is_default=True,
            )
        )

        # 2. Recommended Options
        recommended = self.catalog.get_recommended_icons(
            self.node_kind, self.resource_type
        )
        for opt in recommended:
            self.option_list.add_option(
                IconPickerOption(
                    prompt=f"{opt.symbol}  {opt.name}",
                    symbol=opt.symbol,
                )
            )

        # 3. Custom Option
        self.option_list.add_option(
            IconPickerOption(
                prompt="Custom...",
                symbol="",
                is_custom=True,
            )
        )

        # Reset selection highlight
        self.option_list.highlighted = 0

    def set_node_type(self, node_kind: str, resource_type: str | None) -> None:
        """Update node classification and adjust proposed default if unchanged."""
        old_default = self.catalog.get_default_icon(self.node_kind, self.resource_type)
        new_default = self.catalog.get_default_icon(node_kind, resource_type)

        self.node_kind = node_kind
        self.resource_type = resource_type

        self.populate_options()

        try:
            input_widget = self.query_one(f"#{self.input_id}", Input)
            current_val = input_widget.value.strip()

            # If current icon is empty or matches previous default,
            # suggest the new default icon.
            if not current_val or current_val == old_default:
                self._is_accepting_option = True
                input_widget.value = new_default
                input_widget.cursor_position = len(new_default)
        except NoMatches:
            pass

    def update_suggestions_position(self) -> None:
        """Position the OptionList overlay directly below the input field."""
        try:
            input_widget = self.query_one(f"#{self.input_id}", Input)
            parent = self.option_list.parent
            if parent is None:
                return

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
        except (NoMatches, AttributeError):
            pass

    def handle_input_key(self, event: events.Key) -> bool:
        """Handle key interception from the inner Input widget."""
        key = event.key
        aliases = getattr(event, "aliases", [])
        is_shift_enter = key == "shift+enter" or "shift+enter" in aliases

        # Global shortcuts
        if is_shift_enter:
            self.hide_suggestions()
            if self.screen:
                self.screen.focus_next()
            return True

        if key == "escape":
            if self.is_suggestions_visible:
                self.hide_suggestions()
                return True
            return False

        if key == "tab":
            self.hide_suggestions()
            return False

        if not self.is_suggestions_visible:
            if key in ("down", "up", "ctrl+j", "ctrl+k"):
                self.show_suggestions()
                return True
            return False

        # Popup navigation shortcuts
        if key in ("down", "ctrl+n", "ctrl+j") or "ctrl+j" in aliases:
            self.move_highlight(1)
            return True
        elif key in ("up", "ctrl+p", "ctrl+k") or "ctrl+k" in aliases:
            self.move_highlight(-1)
            return True
        elif key == "enter":
            highlighted = self.option_list.highlighted
            if highlighted is not None:
                option = self.option_list.get_option_at_index(highlighted)
                if isinstance(option, IconPickerOption):
                    self.accept_highlighted_option(option)
            else:
                self.hide_suggestions()
            return True

        return False

    def move_highlight(self, direction: int) -> None:
        """Move option list highlight with wraparound."""
        count = self.option_list.option_count
        if count == 0:
            return
        current = self.option_list.highlighted
        if current is None:
            new_idx = 0 if direction > 0 else count - 1
        else:
            new_idx = (current + direction) % count
        self.option_list.highlighted = new_idx

    def accept_highlighted_option(self, option: IconPickerOption) -> None:
        """Apply selected option's icon symbol or default state."""
        try:
            input_widget = self.query_one(f"#{self.input_id}", Input)
            if option.is_default:
                default_symbol = self.catalog.get_default_icon(
                    self.node_kind, self.resource_type
                )
                self._is_accepting_option = True
                input_widget.value = default_symbol
                input_widget.cursor_position = len(default_symbol)
            elif option.is_custom:
                self._is_accepting_option = True
                input_widget.value = ""
                input_widget.focus()
            else:
                self._is_accepting_option = True
                input_widget.value = option.symbol
                input_widget.cursor_position = len(option.symbol)

            input_widget.focus()
            self.hide_suggestions()
        except NoMatches:
            pass

    def show_suggestions(self) -> None:
        """Display option list overlay."""
        self.update_suggestions_position()
        self.option_list.display = True
        self.is_suggestions_visible = True

    def hide_suggestions(self) -> None:
        """Hide option list overlay."""
        self.option_list.display = False
        self.is_suggestions_visible = False

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle real-time suggestions updates."""
        if event.input.id != self.input_id:
            return

        if self._is_accepting_option:
            self._is_accepting_option = False
            return

        # Only show suggestions if the input widget is currently focused.
        # This prevents asynchronous mount-time change events from opening
        # the suggestions popup.
        try:
            input_widget = self.query_one(f"#{self.input_id}", Input)
            if not input_widget.has_focus:
                return
        except NoMatches:
            return

        self.show_suggestions()

    def on_blur(self, event: events.Blur) -> None:
        """Defer blur handling to verify if focus has left completely."""
        self.call_after_refresh(self._handle_blur_deferred)

    def _handle_blur_deferred(self) -> None:
        """Hide options only if focus left both Input and OptionList."""
        if not self.is_mounted:
            return
        try:
            focused = self.screen.focused
        except Exception:
            focused = None

        try:
            inner_input = self.query_one(f"#{self.input_id}", Input)
        except NoMatches:
            inner_input = None

        if focused in (self.option_list, inner_input):
            return

        self.hide_suggestions()
