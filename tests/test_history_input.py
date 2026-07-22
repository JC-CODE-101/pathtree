"""Tests for HistoryInput widget undo history and selection collapse."""

from pathlib import Path

import pytest
from sqlmodel import Session
from textual.app import App, ComposeResult

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.widgets.history_input import HistoryInput
from pathtree.ui.widgets.path_autocomplete import PathAutocomplete


class HistoryInputTestApp(App[None]):
    """Test application for isolating HistoryInput behaviors."""

    def compose(self) -> ComposeResult:
        yield HistoryInput(value="Initial Name", id="input-name")
        yield HistoryInput(value="Initial Desc", id="input-desc")


@pytest.mark.asyncio
async def test_independent_history() -> None:
    """Verify that HistoryInput fields maintain independent undo histories."""
    app = HistoryInputTestApp()
    async with app.run_test() as pilot:
        name_input = app.screen.query_one("#input-name", HistoryInput)
        desc_input = app.screen.query_one("#input-desc", HistoryInput)

        # Focus name and select all, then backspace to clear
        name_input.focus()
        name_input.selection = (0, len(name_input.value))
        await pilot.pause()
        await pilot.press("backspace")
        assert name_input.value == ""
        assert len(name_input._undo_history) == 1

        # Focus desc and select all, then backspace to clear
        desc_input.focus()
        desc_input.selection = (0, len(desc_input.value))
        await pilot.pause()
        await pilot.press("backspace")
        assert desc_input.value == ""
        assert len(desc_input._undo_history) == 1

        # Press ctrl+z on desc_input, it should restore desc but NOT name
        await pilot.press("ctrl+z")
        assert desc_input.value == "Initial Desc"
        assert name_input.value == ""

        # Press ctrl+z on name_input, it should restore name
        name_input.focus()
        await pilot.press("ctrl+z")
        assert name_input.value == "Initial Name"
        assert desc_input.value == "Initial Desc"


@pytest.mark.asyncio
async def test_ctrl_z_restores_fields(session: Session, tmp_path: Path) -> None:
    """Verify Ctrl+Z restores deleted fields inside EditNodeDialog."""
    repo = NodeRepository(session)
    _ = repo.create(
        Node(
            name="My Node",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            description="My Description",
            icon="My Icon",
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger edit dialog 'e'
        await pilot.press("e")
        assert isinstance(app.screen, EditNodeDialog)
        dialog = app.screen

        name_input = dialog.query_one("#input-name", HistoryInput)
        path_wrapper = dialog.query_one("#input-path-wrapper", PathAutocomplete)
        path_input = path_wrapper.query_one("#input-path")
        desc_input = dialog.query_one("#input-description", HistoryInput)
        icon_input = dialog.query_one("#input-icon", HistoryInput)

        # 1. Test Name Undo
        name_input.focus()
        name_input.selection = (0, len(name_input.value))
        await pilot.pause()
        await pilot.press("backspace")
        assert name_input.value == ""
        await pilot.press("ctrl+z")
        assert name_input.value == "My Node"

        # 2. Test Path Undo
        path_input.focus()
        path_input.selection = (0, len(path_input.value))
        await pilot.pause()
        await pilot.press("backspace")
        assert path_input.value == ""
        await pilot.press("ctrl+z")
        assert path_input.value == str(tmp_path)

        # 3. Test Description Undo
        desc_input.focus()
        desc_input.selection = (0, len(desc_input.value))
        await pilot.pause()
        await pilot.press("backspace")
        assert desc_input.value == ""
        await pilot.press("ctrl+z")
        assert desc_input.value == "My Description"

        # 4. Test Icon Undo
        icon_input.focus()
        icon_input.selection = (0, len(icon_input.value))
        await pilot.pause()
        await pilot.press("backspace")
        assert icon_input.value == ""
        await pilot.press("ctrl+z")
        assert icon_input.value == "My Icon"

        # Cancel dialog
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_shift_e_behavior() -> None:
    """Verify Shift+E selection collapse, cursor movement, and focus retention."""
    app = HistoryInputTestApp()
    async with app.run_test() as pilot:
        name_input = app.screen.query_one("#input-name", HistoryInput)

        # Focus and select all
        name_input.focus()
        name_input.selection = (0, len(name_input.value))
        await pilot.pause()

        # Press E (Shift+E)
        await pilot.press("E")
        assert name_input.value == "Initial Name"
        # Selection must be cleared and cursor placed at the end
        assert (name_input.selection.start, name_input.selection.end) == (
            len(name_input.value),
            len(name_input.value),
        )
        assert app.focused == name_input

        # Typing after selection collapse should append text normally
        await pilot.press("x")
        assert name_input.value == "Initial Namex"

        # When there is no selection, Shift+E behaves normally and types "E"
        await pilot.press("E")
        assert name_input.value == "Initial NamexE"


@pytest.mark.asyncio
async def test_shift_e_does_not_submit_or_close_dialog(session: Session) -> None:
    """Verify Shift+E does not submit or close EditNodeDialog."""
    repo = NodeRepository(session)
    repo.create(
        Node(
            name="Dialog Node",
            node_kind="workspace",
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Trigger edit dialog 'e'
        await pilot.press("e")
        assert isinstance(app.screen, EditNodeDialog)
        dialog = app.screen

        name_input = dialog.query_one("#input-name", HistoryInput)
        name_input.focus()
        name_input.selection = (0, len(name_input.value))
        await pilot.pause()

        # Press E (Shift+E) to collapse selection
        await pilot.press("E")
        await pilot.pause()

        # Dialog must remain open
        assert app.screen == dialog
        assert name_input.value == "Dialog Node"
        assert (name_input.selection.start, name_input.selection.end) == (
            len(name_input.value),
            len(name_input.value),
        )

        # Cancel dialog
        await pilot.press("escape")


@pytest.mark.asyncio
async def test_autocomplete_shortcuts_still_work(tmp_path: Path, monkeypatch) -> None:
    """Verify autocomplete shortcuts work perfectly as a regression check."""
    (tmp_path / "blocks").mkdir()
    monkeypatch.chdir(tmp_path)

    app = App()

    class CustomApp(App[None]):
        def compose(self) -> ComposeResult:
            yield PathAutocomplete(id="input-path")

    app = CustomApp()
    async with app.run_test() as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Type partial path
        input_path.value = "b"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        # Tab must accept the suggestion
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_path.value == "blocks/"

        # Enter must close suggestions
        input_path.value = "blocks"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        await pilot.press("enter")
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is False

        # Escape closes suggestions first
        input_path.value = "b"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is False
