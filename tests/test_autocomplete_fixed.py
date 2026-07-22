"""Focused tests for Path Autocomplete tilde normalization and keyboard semantics."""

import os
from pathlib import Path

import pytest
from sqlmodel import Session
from textual.app import App, ComposeResult

from pathtree.database.repository import NodeRepository
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.widgets.path_autocomplete import PathAutocomplete


class AutocompleteTestApp(App[None]):
    """Simple test app to isolate PathAutocomplete testing."""

    def compose(self) -> ComposeResult:
        yield PathAutocomplete(id="input-path")


class KeyboardShortcutTestApp(App[None]):
    """Test app with PathAutocomplete and a subsequent Input widget."""

    def compose(self) -> ComposeResult:
        from textual.widgets import Input

        yield PathAutocomplete(id="input-path")
        yield Input(id="input-description")


@pytest.mark.asyncio
async def test_path_normalization_tilde_behavior(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    """Test tilde path expansion, absolute normalization, editing, and failures."""
    node_service = NodeService(NodeRepository(session))

    # Mock expanduser to point ~ to tmp_path
    monkeypatch.setattr(
        Path,
        "expanduser",
        lambda self: Path(str(self).replace("~", str(tmp_path))),
    )
    monkeypatch.setattr(os.path, "expanduser", lambda p: p.replace("~", str(tmp_path)))

    # 1. Accepted and persisted in absolute normalized form
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    real_dir = tmp_path / "ws_data"
    real_dir.mkdir()

    # Create using a tilde path
    node = node_service.create_node(
        name="Dir Node",
        node_kind="resource",
        resource_type="directory",
        parent_id=ws.id,
        path="~/ws_data",
    )
    # It must be saved as the absolute path
    assert node.path == str(real_dir.resolve())

    # 2. Activating the resulting node succeeds
    activated_path = node_service.resolve_node_path(node.id)
    assert activated_path == real_dir.resolve()

    # 3. Editing to a ~/... path works and persists absolute form
    another_real_dir = tmp_path / "another_ws_data"
    another_real_dir.mkdir()

    updated_node = node_service.update_node(node.id, path="~/another_ws_data")
    assert updated_node.path == str(another_real_dir.resolve())

    # 4. Fail validation during directory activation/resolution
    node_service.update_node(node.id, path="~/nonexistent_dir")
    from pathtree.services.node_service import PathNotFoundError

    with pytest.raises(PathNotFoundError) as exc:
        node_service.resolve_node_path(node.id)
    assert "does not exist" in str(exc.value)


@pytest.mark.asyncio
async def test_autocomplete_keyboard_semantics_and_scoping(
    tmp_path: Path, monkeypatch
) -> None:
    """Test autocomplete keyboard semantics: Tab accepts, Enter closes."""
    root = tmp_path / "root"
    code = root / "code"
    python = code / "python"
    python.mkdir(parents=True)

    monkeypatch.chdir(tmp_path)

    app = KeyboardShortcutTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Type to trigger suggestions
        input_path.value = "root/co"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        # 1. TAB accepts the highlighted suggestion
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_path.value == "root/code/"
        # Since ends with "/", immediately scan/show children (chained)
        assert p_widget.is_suggestions_visible is True
        assert p_widget.option_list.option_count == 1
        assert str(p_widget.option_list.get_option_at_index(0).prompt) == "python/"

        # 2. Repeated Tab scopes through multiple directory levels
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_path.value == "root/code/python/"
        # Re-scans python/ which is empty, so displays "No matching directories."
        assert p_widget.is_suggestions_visible is True
        assert "No matching" in str(p_widget.option_list.get_option_at_index(0).prompt)

        # 3. Enter does NOT accept suggestions, keeps path, closes popup
        input_path.value = "root/co"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        await pilot.press("enter")
        await pilot.pause(0.05)
        assert input_path.value == "root/co"
        assert p_widget.is_suggestions_visible is False

        # 4. Shift+Space explicitly reopens suggestions for the current path
        await pilot.press("shift+space")
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        assert input_path.value == "root/co"

        # Close with escape
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is False

        # 5. Typing '/' after closing suggestions reopens them
        input_path.value = "root/code/"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True
        assert str(p_widget.option_list.get_option_at_index(0).prompt) == "python/"


@pytest.mark.asyncio
async def test_add_and_edit_dialog_autocompletion_flow(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    """Verify autocomplete behavior on Add/Edit dialogs."""
    node_service = NodeService(NodeRepository(session))
    ws = node_service.create_node(name="Workspace", node_kind="workspace")

    (tmp_path / "suggested_folder").mkdir()
    monkeypatch.chdir(tmp_path)

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 24)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # 1. AddNodeDialog Autocomplete Flow
        await pilot.press("a")
        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)

        await pilot.click("#radio-directory")
        await pilot.pause(0.01)

        dialog.query_one("#input-name").value = "New Dir Node"
        dialog.query_one("#select-parent").value = ws.id

        p_widget = dialog.query_one("#input-path-wrapper", PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Type path
        input_path.value = "s"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        # Enter must close suggestions and NOT accept
        await pilot.press("enter")
        await pilot.pause(0.05)
        assert input_path.value == "s"
        assert p_widget.is_suggestions_visible is False

        # Open suggestions again with Shift+Space
        await pilot.press("shift+space")
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        # Tab accepts suggestion
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_path.value == "suggested_folder/"

        # Escape closes suggestions
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is False

        # Escape again closes AddNodeDialog
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.screen.id == "main-screen"
