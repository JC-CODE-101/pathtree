from pathlib import Path

import pytest
from sqlmodel import Session
from textual.app import App, ComposeResult

from pathtree.database.repository import NodeRepository
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.widgets.path_autocomplete import PathAutocomplete, PathAutocompleteMode


class ContextTestApp(App[None]):
    """Test app with context-aware PathAutocomplete."""

    def compose(self) -> ComposeResult:
        yield PathAutocomplete(id="input-path")


@pytest.mark.asyncio
async def test_directory_vs_file_mode_filtering_sorting_and_empty_text(
    tmp_path: Path, monkeypatch
) -> None:
    """Test required behaviors:
    - Directory mode shows directories and hides files;
    - File mode shows directories and files;
    - File mode displays .md files;
    - File mode also displays non-.md files;
    - Empty-result text is accurate for each mode;
    - Sorting is deterministic (directories first, then files, alphabetically).
    """
    (tmp_path / "subdir_b").mkdir()
    (tmp_path / "subdir_a").mkdir()
    (tmp_path / "file_b.md").write_text("content")
    (tmp_path / "file_a.txt").write_text("content")

    monkeypatch.chdir(tmp_path)

    app = ContextTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # 1. Directory Mode (default)
        p_widget.set_mode(PathAutocompleteMode.DIRECTORY)
        input_path.value = "s"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        # Verify only directories starting with 's' are shown (sorted alphabetically)
        prompts = [
            str(p_widget.option_list.get_option_at_index(i).prompt)
            for i in range(p_widget.option_list.option_count)
        ]
        assert prompts == ["subdir_a/", "subdir_b/"]

        # Test empty result text in Directory mode
        input_path.value = "nonexistent"
        await pilot.pause(0.05)
        empty_prompt = str(p_widget.option_list.get_option_at_index(0).prompt)
        assert empty_prompt == "No matching directories."

        # 2. File Mode
        p_widget.set_mode(PathAutocompleteMode.FILE)

        # Empty input to clear
        input_path.value = ""
        await pilot.pause(0.05)

        # Trigger autocomplete
        input_path.value = "s"
        await pilot.pause(0.05)

        # Since 'subdir_a' and 'subdir_b' start with 's', and no files start with 's'
        prompts = [
            str(p_widget.option_list.get_option_at_index(i).prompt)
            for i in range(p_widget.option_list.option_count)
        ]
        assert prompts == ["subdir_a/", "subdir_b/"]

        # If prefix matches both files and directories, trigger shift+space to list all
        input_path.value = ""
        await pilot.pause(0.05)
        await pilot.press("shift+space")
        await pilot.pause(0.05)

        prompts = [
            str(p_widget.option_list.get_option_at_index(i).prompt)
            for i in range(p_widget.option_list.option_count)
        ]
        # Should be directories first, then files, both alphabetically
        assert prompts == ["subdir_a/", "subdir_b/", "file_a.txt", "file_b.md"]

        # Test empty result text in File mode
        input_path.value = "nonexistent"
        await pilot.pause(0.05)
        empty_prompt = str(p_widget.option_list.get_option_at_index(0).prompt)
        assert empty_prompt == "No matching files or directories."


@pytest.mark.asyncio
async def test_selection_and_continued_navigation(tmp_path: Path, monkeypatch) -> None:
    """Test required behaviors:
    - Selecting a file inserts the complete path;
    - Selecting a directory allows continued navigation.
    """
    (tmp_path / "subdir_a").mkdir()
    (tmp_path / "subdir_a" / "nested_file.txt").write_text("content")
    (tmp_path / "file_a.txt").write_text("content")

    monkeypatch.chdir(tmp_path)

    app = ContextTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Set mode to FILE
        p_widget.set_mode(PathAutocompleteMode.FILE)

        # Type 'f' to match file
        input_path.value = "f"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        # Highlight and select the file
        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_path.value == "file_a.txt"
        assert p_widget.is_suggestions_visible is False

        # Clear and try directory selection for continued navigation
        input_path.value = "sub"
        await pilot.pause(0.05)
        assert p_widget.is_suggestions_visible is True

        await pilot.press("tab")
        await pilot.pause(0.05)
        assert input_path.value == "subdir_a/"
        # Should still be visible and showing contents of subdir_a/
        assert p_widget.is_suggestions_visible is True

        prompts = [
            str(p_widget.option_list.get_option_at_index(i).prompt)
            for i in range(p_widget.option_list.option_count)
        ]
        assert prompts == ["nested_file.txt"]


@pytest.mark.asyncio
async def test_immediate_mode_switching_updates_suggestions(
    tmp_path: Path, monkeypatch
) -> None:
    """Test required behaviors:
    - Switching Directory -> File updates suggestions immediately;
    - Switching File -> Directory hides files immediately.
    """
    (tmp_path / "subdir_a").mkdir()
    (tmp_path / "file_a.txt").write_text("content")

    monkeypatch.chdir(tmp_path)

    app = ContextTestApp()
    async with app.run_test(size=(80, 24)) as pilot:
        p_widget = app.screen.query_one(PathAutocomplete)
        input_path = p_widget.query_one("#input-path")
        input_path.focus()

        # Start in Directory mode and type nothing, trigger space
        p_widget.set_mode(PathAutocompleteMode.DIRECTORY)
        await pilot.press("shift+space")
        await pilot.pause(0.05)

        prompts = [
            str(p_widget.option_list.get_option_at_index(i).prompt)
            for i in range(p_widget.option_list.option_count)
        ]
        assert prompts == ["subdir_a/"]

        # Switch Directory -> File: suggestions must update immediately
        p_widget.set_mode(PathAutocompleteMode.FILE)
        await pilot.pause(0.05)

        prompts = [
            str(p_widget.option_list.get_option_at_index(i).prompt)
            for i in range(p_widget.option_list.option_count)
        ]
        assert prompts == ["subdir_a/", "file_a.txt"]

        # Switch File -> Directory: suggestions must update immediately, hiding files
        p_widget.set_mode(PathAutocompleteMode.DIRECTORY)
        await pilot.pause(0.05)

        prompts = [
            str(p_widget.option_list.get_option_at_index(i).prompt)
            for i in range(p_widget.option_list.option_count)
        ]
        assert prompts == ["subdir_a/"]


@pytest.mark.asyncio
async def test_add_and_edit_dialogs_use_correct_mode(
    session: Session, tmp_path: Path, monkeypatch
) -> None:
    """Test required behavior:
    - Add and Edit dialogs both use the correct mode.
    """
    node_service = NodeService(NodeRepository(session))
    ws = node_service.create_node(name="Workspace", node_kind="workspace")
    dir_node = node_service.create_node(
        name="Dir Node",
        node_kind="resource",
        resource_type="directory",
        parent_id=ws.id,
        path=str(tmp_path),
    )

    real_file = tmp_path / "my_real_file.txt"
    real_file.write_text("hello")

    file_node = node_service.create_node(
        name="File Node",
        node_kind="resource",
        resource_type="file",
        parent_id=ws.id,
        path=str(real_file),
    )

    monkeypatch.chdir(tmp_path)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 24)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # 1. Test AddNodeDialog mode selection behavior
        await pilot.press("a")
        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)

        p_widget = dialog.query_one("#input-path-wrapper", PathAutocomplete)

        # Initially workspace -> DIRECTORY mode
        assert p_widget._mode == PathAutocompleteMode.DIRECTORY

        # Switch to Folder -> DIRECTORY mode
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        assert p_widget._mode == PathAutocompleteMode.DIRECTORY

        # Switch to Directory -> DIRECTORY mode
        await pilot.click("#radio-directory")
        await pilot.pause(0.01)
        assert p_widget._mode == PathAutocompleteMode.DIRECTORY

        # Switch to File -> FILE mode
        await pilot.click("#radio-file")
        await pilot.pause(0.01)
        assert p_widget._mode == PathAutocompleteMode.FILE

        # Switch back to Workspace -> DIRECTORY mode
        await pilot.click("#radio-workspace")
        await pilot.pause(0.01)
        assert p_widget._mode == PathAutocompleteMode.DIRECTORY

        # Close AddNodeDialog
        await pilot.press("escape")
        await pilot.pause(0.05)

        # 2. Test EditNodeDialog for Directory node
        edit_dir_dialog = EditNodeDialog(node_service=node_service, node_id=dir_node.id)

        app.push_screen(edit_dir_dialog)
        await pilot.pause(0.05)

        p_widget_edit = edit_dir_dialog.query_one(
            "#input-path-wrapper", PathAutocomplete
        )
        assert p_widget_edit._mode == PathAutocompleteMode.DIRECTORY

        await pilot.press("escape")
        await pilot.pause(0.05)

        # 3. Test EditNodeDialog for File node
        edit_file_dialog = EditNodeDialog(
            node_service=node_service, node_id=file_node.id
        )

        app.push_screen(edit_file_dialog)
        await pilot.pause(0.05)

        p_widget_edit_file = edit_file_dialog.query_one(
            "#input-path-wrapper", PathAutocomplete
        )
        assert p_widget_edit_file._mode == PathAutocompleteMode.FILE

        await pilot.press("escape")
        await pilot.pause(0.05)
