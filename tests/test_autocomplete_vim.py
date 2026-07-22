"""Tests for Vim-style (Ctrl+J / Ctrl+K) autocomplete navigation."""

from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from pathtree.ui.widgets.path_autocomplete import PathAutocomplete


class VimAutocompleteTestApp(App[None]):
    """Test app with PathAutocomplete to verify key bindings."""

    def compose(self) -> ComposeResult:
        yield PathAutocomplete(id="input-path")


@pytest.mark.asyncio
async def test_ctrl_j_moves_highlight_down(tmp_path: Path, monkeypatch) -> None:
    """Verify Ctrl+J moves highlighted suggestion down by one entry."""
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "dir_c").mkdir()
    monkeypatch.chdir(tmp_path)

    app = VimAutocompleteTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Type 'd' to trigger suggestions
        input_path.value = "d"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        assert p_widget.option_list.highlighted == 0

        # Ctrl+J moves highlight down
        await pilot.press("ctrl+j")
        await pilot.pause()
        assert p_widget.option_list.highlighted == 1

        # Ctrl+J moves highlight down again
        await pilot.press("ctrl+j")
        await pilot.pause()
        assert p_widget.option_list.highlighted == 2


@pytest.mark.asyncio
async def test_ctrl_k_moves_highlight_up(tmp_path: Path, monkeypatch) -> None:
    """Verify Ctrl+K moves highlighted suggestion up by one entry (with wrapping)."""
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_b").mkdir()
    (tmp_path / "dir_c").mkdir()
    monkeypatch.chdir(tmp_path)

    app = VimAutocompleteTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Type 'd' to trigger suggestions
        input_path.value = "d"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        assert p_widget.option_list.highlighted == 0

        # Ctrl+K moves highlight up (wraps around to the end)
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert p_widget.option_list.highlighted == 2

        # Ctrl+K moves highlight up again
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert p_widget.option_list.highlighted == 1


@pytest.mark.asyncio
async def test_ctrl_j_k_scrolls_correctly_long_list(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify Ctrl+J and Ctrl+K scroll the popup correctly in long lists."""
    for i in range(1, 21):
        (tmp_path / f"dir_{i:02d}").mkdir()
    monkeypatch.chdir(tmp_path)

    app = VimAutocompleteTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Set maximum height to force scrolling
        p_widget.option_list.styles.height = 4

        # Type 'd' to trigger suggestions
        input_path.value = "d"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        assert p_widget.option_list.highlighted == 0
        assert p_widget.option_list.scroll_offset.y == 0

        # Move down repeatedly via Ctrl+J to item index 10 (needs scroll)
        for _ in range(10):
            await pilot.press("ctrl+j")
            await pilot.pause()

        assert p_widget.option_list.highlighted == 10
        # Scroll position should have updated (scrolled down)
        assert p_widget.option_list.scroll_offset.y > 0

        # Scroll position should decrease when moving back up with Ctrl+K
        last_scroll_y = p_widget.option_list.scroll_offset.y
        for _ in range(5):
            await pilot.press("ctrl+k")
            await pilot.pause()

        assert p_widget.option_list.highlighted == 5
        assert p_widget.option_list.scroll_offset.y < last_scroll_y


@pytest.mark.asyncio
async def test_tab_accepts_after_ctrl_j_k(tmp_path: Path, monkeypatch) -> None:
    """Verify Tab still accepts the currently highlighted item.

    Must work after Ctrl+J/Ctrl+K navigation.
    """
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_b").mkdir()
    monkeypatch.chdir(tmp_path)

    app = VimAutocompleteTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Type 'd' to trigger suggestions
        input_path.value = "d"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        # Navigate to "dir_b/" with Ctrl+J
        await pilot.press("ctrl+j")
        await pilot.pause()
        assert p_widget.option_list.highlighted == 1

        # Press Tab to accept
        await pilot.press("tab")
        await pilot.pause()
        assert input_path.value == "dir_b/"


@pytest.mark.asyncio
async def test_arrow_keys_behave_exactly_as_before(tmp_path: Path, monkeypatch) -> None:
    """Verify Arrow keys (Up/Down) still behave exactly as before."""
    (tmp_path / "dir_a").mkdir()
    (tmp_path / "dir_b").mkdir()
    monkeypatch.chdir(tmp_path)

    app = VimAutocompleteTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Type 'd' to trigger suggestions
        input_path.value = "d"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        assert p_widget.option_list.highlighted == 0

        # Down arrow moves highlight down
        await pilot.press("down")
        await pilot.pause()
        assert p_widget.option_list.highlighted == 1

        # Up arrow moves highlight up
        await pilot.press("up")
        await pilot.pause()
        assert p_widget.option_list.highlighted == 0


@pytest.mark.asyncio
async def test_ctrl_j_k_no_effect_when_suggestions_hidden(
    tmp_path: Path, monkeypatch
) -> None:
    """Verify Ctrl+J and Ctrl+K have no effect when suggestions are hidden."""
    (tmp_path / "dir_a").mkdir()
    monkeypatch.chdir(tmp_path)

    app = VimAutocompleteTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Suggestions are hidden initially
        assert p_widget.is_suggestions_visible is False

        # Pressing Ctrl+J should not trigger suggestions visibility or raise error
        await pilot.press("ctrl+j")
        await pilot.pause()
        assert p_widget.is_suggestions_visible is False

        # Pressing Ctrl+K should not trigger suggestions visibility or raise error
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert p_widget.is_suggestions_visible is False
