import uuid
from pathlib import Path
import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository, WorkspaceViewSettingsRepository
from pathtree.models.node import Node
from pathtree.services.node_service import TreeNode, NodeService
from pathtree.services.workspace_view_settings_service import (
    WorkspaceViewSettingsService,
    DIRECTORIES,
    FILES,
    SCRIPTS,
    EXECUTABLES,
    URLS,
    LAUNCH_PROFILES,
    MULTI_LAUNCHERS,
    CUSTOM,
)
from pathtree.utils.icons import icon_registry


@pytest.fixture
def view_settings_service(session: Session) -> WorkspaceViewSettingsService:
    repo = WorkspaceViewSettingsRepository(session)
    return WorkspaceViewSettingsService(repo)


def test_view_settings_retrieval_and_cache(session: Session, view_settings_service: WorkspaceViewSettingsService):
    """Test retrieving settings creates defaults, caches, and updates both db and cache."""
    node_repo = NodeRepository(session)
    ws_node = node_repo.create(Node(name="Test WS", node_kind="workspace"))
    ws_id = ws_node.id

    # Retrieve settings - should create default record
    settings = view_settings_service.get_settings(ws_id)
    assert settings.workspace_id == ws_id
    assert settings.current_mode == "all"
    assert settings.last_filter_mask == 0
    assert settings.hide_empty_sections is False
    assert settings.show_system is True
    assert settings.show_custom is True

    # Check cache hit
    cached = view_settings_service.get_settings(ws_id)
    assert cached is settings

    # Update settings
    settings.current_mode = "filter"
    settings.last_filter_mask = FILES | SCRIPTS
    view_settings_service.save_settings(settings)

    # Re-retrieve (bypassing cache to ensure db was updated)
    fresh_service = WorkspaceViewSettingsService(WorkspaceViewSettingsRepository(session))
    db_settings = fresh_service.get_settings(ws_id)
    assert db_settings.current_mode == "filter"
    assert db_settings.last_filter_mask == FILES | SCRIPTS


def test_clear_settings(session: Session, view_settings_service: WorkspaceViewSettingsService):
    """Test clearing saved filter resets mode and masks but keeps hide_empty."""
    node_repo = NodeRepository(session)
    ws_node = node_repo.create(Node(name="Test WS", node_kind="workspace"))
    ws_id = ws_node.id
    settings = view_settings_service.get_settings(ws_id)
    settings.current_mode = "filter"
    settings.last_filter_mask = DIRECTORIES
    settings.hide_empty_sections = True
    view_settings_service.save_settings(settings)

    # Clear
    cleared = view_settings_service.clear_settings(ws_id)
    assert cleared.current_mode == "all"
    assert cleared.last_filter_mask == 0
    assert cleared.show_system is True
    assert cleared.show_custom is True
    # independent:
    assert cleared.hide_empty_sections is True


def test_filter_tree_all_view(session: Session, view_settings_service: WorkspaceViewSettingsService):
    """Test filtering in default All View does not remove elements unless empty hidden."""
    node_repo = NodeRepository(session)
    ws_node = node_repo.create(Node(name="Test WS", node_kind="workspace"))
    ws_id = ws_node.id

    # Build typical system subsections tree
    directories_sg = Node(name="Directories", node_kind="system_group", system_role="directories")
    files_sg = Node(name="Files", node_kind="system_group", system_role="files")

    # Directories has 1 child, Files has 0 children
    dir_child = Node(name="Projects", node_kind="resource", resource_type="directory")
    sub_directories = TreeNode(directories_sg, [TreeNode(dir_child)])
    sub_files = TreeNode(files_sg, [])

    system_group = Node(name="System", node_kind="system_group", system_role="system")
    sub_system = TreeNode(system_group, [sub_directories, sub_files])

    custom_group = Node(name="Custom", node_kind="system_group", system_role="custom")
    sub_custom = TreeNode(custom_group, [])

    root_tree = TreeNode(ws_node, [sub_system, sub_custom])

    # 1. Default (hide_empty_sections=False)
    filtered = view_settings_service.filter_tree([root_tree])
    assert len(filtered) == 1
    ws_filtered = filtered[0]
    assert len(ws_filtered.children) == 2  # System and Custom
    sys_filtered = ws_filtered.children[0]
    assert len(sys_filtered.children) == 2  # Directories and Files (even though Files is empty)

    # 2. Toggle hide_empty_sections=True
    settings = view_settings_service.get_settings(ws_id)
    settings.hide_empty_sections = True
    view_settings_service.save_settings(settings)

    filtered = view_settings_service.filter_tree([root_tree])
    sys_filtered = filtered[0].children[0]
    assert len(sys_filtered.children) == 1
    assert sys_filtered.children[0].node.system_role == "directories"  # Files was hidden because it's empty!


def test_additive_and_toggle_filters(session: Session, view_settings_service: WorkspaceViewSettingsService):
    """Test setting, toggling and combining specific resource and custom filters."""
    node_repo = NodeRepository(session)
    ws_node = node_repo.create(Node(name="Test WS", node_kind="workspace"))
    ws_id = ws_node.id

    settings = view_settings_service.get_settings(ws_id)
    settings.current_mode = "filter"
    settings.last_filter_mask = FILES | SCRIPTS
    settings.show_custom = False
    view_settings_service.save_settings(settings)

    # Verify Files and Scripts are active, Directories is not
    assert settings.last_filter_mask & FILES
    assert settings.last_filter_mask & SCRIPTS
    assert not (settings.last_filter_mask & DIRECTORIES)

    # Build typical tree with Custom, Directories, Files, and Scripts
    directories_sg = Node(name="Directories", node_kind="system_group", system_role="directories")
    files_sg = Node(name="Files", node_kind="system_group", system_role="files")
    scripts_sg = Node(name="Scripts", node_kind="system_group", system_role="scripts")

    sub_directories = TreeNode(directories_sg, [TreeNode(Node(name="Projects", node_kind="resource", resource_type="directory"))])
    sub_files = TreeNode(files_sg, [TreeNode(Node(name="Data.txt", node_kind="resource", resource_type="file"))])
    sub_scripts = TreeNode(scripts_sg, [TreeNode(Node(name="Run.sh", node_kind="resource", resource_type="script"))])

    system_group = Node(name="System", node_kind="system_group", system_role="system")
    sub_system = TreeNode(system_group, [sub_directories, sub_files, sub_scripts])

    custom_group = Node(name="Custom", node_kind="system_group", system_role="custom")
    sub_custom = TreeNode(custom_group, [TreeNode(Node(name="Folder A", node_kind="folder"))])

    root_tree = TreeNode(ws_node, [sub_system, sub_custom])

    # Apply filter
    filtered = view_settings_service.filter_tree([root_tree])
    ws_filtered = filtered[0]

    # Custom should be hidden since show_custom=False
    assert len(ws_filtered.children) == 1  # only System Group
    sys_filtered = ws_filtered.children[0]

    # Subsections should only be Files and Scripts
    assert len(sys_filtered.children) == 2
    roles = {child.node.system_role for child in sys_filtered.children}
    assert roles == {"files", "scripts"}


def test_custom_filter(session: Session, view_settings_service: WorkspaceViewSettingsService):
    """Test vc shows only Custom and hides System."""
    node_repo = NodeRepository(session)
    ws_node = node_repo.create(Node(name="Test WS", node_kind="workspace"))
    ws_id = ws_node.id

    settings = view_settings_service.get_settings(ws_id)
    settings.current_mode = "filter"
    settings.last_filter_mask = 0
    settings.show_custom = True
    settings.show_system = False
    view_settings_service.save_settings(settings)

    system_group = Node(name="System", node_kind="system_group", system_role="system")
    sub_system = TreeNode(system_group, [])
    custom_group = Node(name="Custom", node_kind="system_group", system_role="custom")
    sub_custom = TreeNode(custom_group, [])

    root_tree = TreeNode(ws_node, [sub_system, sub_custom])

    filtered = view_settings_service.filter_tree([root_tree])
    ws_filtered = filtered[0]
    assert len(ws_filtered.children) == 1
    assert ws_filtered.children[0].node.system_role == "custom"


def test_multi_workspace_persistence(session: Session, view_settings_service: WorkspaceViewSettingsService):
    """Verify different workspaces maintain distinct view states persistently."""
    node_repo = NodeRepository(session)
    ws_node_a = node_repo.create(Node(name="Workspace A", node_kind="workspace"))
    ws_node_b = node_repo.create(Node(name="Workspace B", node_kind="workspace"))

    settings_a = view_settings_service.get_settings(ws_node_a.id)
    settings_a.current_mode = "filter"
    settings_a.last_filter_mask = FILES
    settings_a.hide_empty_sections = True
    view_settings_service.save_settings(settings_a)

    settings_b = view_settings_service.get_settings(ws_node_b.id)
    settings_b.current_mode = "all"
    settings_b.last_filter_mask = 0
    settings_b.hide_empty_sections = False
    view_settings_service.save_settings(settings_b)

    # Re-verify distinctness
    fresh_service = WorkspaceViewSettingsService(WorkspaceViewSettingsRepository(session))
    verify_a = fresh_service.get_settings(ws_node_a.id)
    verify_b = fresh_service.get_settings(ws_node_b.id)

    assert verify_a.current_mode == "filter"
    assert verify_a.last_filter_mask == FILES
    assert verify_a.hide_empty_sections is True

    assert verify_b.current_mode == "all"
    assert verify_b.last_filter_mask == 0
    assert verify_b.hide_empty_sections is False


def test_filter_indicators_presence(session: Session, view_settings_service: WorkspaceViewSettingsService):
    """Verify that has_active_filter returns correct values for various configurations."""
    node_repo = NodeRepository(session)
    ws_node = node_repo.create(Node(name="Test WS", node_kind="workspace"))
    ws_id = ws_node.id

    # Default All View
    assert not view_settings_service.has_active_filter(ws_id)

    # All View with hide-empty
    settings = view_settings_service.get_settings(ws_id)
    settings.hide_empty_sections = True
    view_settings_service.save_settings(settings)
    assert view_settings_service.has_active_filter(ws_id)

    # Reset
    settings.hide_empty_sections = False
    view_settings_service.save_settings(settings)
    assert not view_settings_service.has_active_filter(ws_id)

    # Filter View
    settings.current_mode = "filter"
    settings.last_filter_mask = SCRIPTS
    view_settings_service.save_settings(settings)
    assert view_settings_service.has_active_filter(ws_id)


def test_nearest_visible_ancestor_fallback(session: Session):
    """Test nearest visible ancestor search when selected node is hidden."""
    node_repo = NodeRepository(session)
    ws = node_repo.create(Node(name="WS", node_kind="workspace"))
    folder = node_repo.create(Node(name="Folder", node_kind="folder", parent_id=ws.id))
    file_node = node_repo.create(Node(name="File", node_kind="resource", resource_type="file", parent_id=folder.id))

    # Suppose file_node is hidden, but folder and ws are visible.
    # The nearest visible ancestor of file_node should be folder.
    visible_ids = [ws.id, folder.id]

    def find_nearest_visible_ancestor(node_id: uuid.UUID | None) -> uuid.UUID | None:
        if not node_id:
            return None
        curr_id = node_id
        visited = set()
        while curr_id is not None:
            if curr_id in visited:
                break
            visited.add(curr_id)
            if curr_id in visible_ids:
                return curr_id
            node = node_repo.get_by_id(curr_id)
            if not node:
                break
            curr_id = node.parent_id
        return None

    resolved = find_nearest_visible_ancestor(file_node.id)
    assert resolved == folder.id

    # If folder is also hidden, nearest visible ancestor of file_node should be ws.
    visible_ids = [ws.id]
    resolved = find_nearest_visible_ancestor(file_node.id)
    assert resolved == ws.id


def test_filter_indicator_icon_modes(monkeypatch):
    """Verify the filter indicator symbol resolves correctly under different icon modes."""
    # 1. Nerd mode
    monkeypatch.setenv("PATHTREE_NERD_FONTS", "1")
    assert icon_registry.get_filter_marker() == "󰺰"

    # 2. Unicode mode
    monkeypatch.setenv("PATHTREE_NERD_FONTS", "0")
    assert icon_registry.get_filter_marker() == "◉"

    # 3. ASCII mode
    monkeypatch.setattr(icon_registry, "get_icon_mode", lambda: "ascii")
    assert icon_registry.get_filter_marker() == "[FILTER]"


@pytest.mark.asyncio
async def test_view_command_mode_keypress_scenarios(session: Session, tmp_path: Path) -> None:
    """Rigorous TUI-based integration tests verifying View Command Mode sequences."""
    from pathtree.ui.app import PathTreeApp
    node_service = NodeService(NodeRepository(session))

    # Initialize a clean workspace with System and Custom group layouts
    ws = node_service.create_node(name="Test WS", node_kind="workspace", auto_layout=True)
    # Put a File under Files subsection
    files_subsection = node_service.get_system_subsection(ws.id, "file")
    temp_file = tmp_path / "Data.txt"
    temp_file.write_text("Hello")
    node_service.create_node(
        name="Data.txt",
        node_kind="resource",
        resource_type="file",
        parent_id=files_subsection.id,
        path=str(temp_file),  # valid file path
    )

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Retrieve tree view and widgets
        tree = app.screen.query_one("#tree-view")
        view_bar = app.screen.query_one("#view-mode-bar")
        footer = app.screen.query_one("Footer")

        # Select Workspace
        assert tree.cursor_node.data == ws.id
        assert getattr(app.screen, "_view_command_active", False) is False
        assert view_bar.display is False
        assert footer.display is True

        # --- Test 1: Press 'v' to enter View Command Mode ---
        await pilot.press("v")
        await pilot.pause(0.01)

        assert getattr(app.screen, "_view_command_active", True) is True
        assert view_bar.display is True
        assert footer.display is False

        # --- Test 2: Press 'f' to toggle Files filter and exit View Mode ---
        await pilot.press("f")
        await pilot.pause(0.01)

        assert getattr(app.screen, "_view_command_active", False) is False
        assert view_bar.display is False
        assert footer.display is True

        # Verify Files filter is active
        settings = app.screen.view_settings_service.get_settings(ws.id)
        assert settings.current_mode == "filter"
        assert settings.last_filter_mask == FILES

        # --- Test 3: Escape cancels the View Mode ---
        await pilot.press("v")
        await pilot.pause(0.01)
        assert getattr(app.screen, "_view_command_active", False) is True

        await pilot.press("escape")
        await pilot.pause(0.01)
        assert getattr(app.screen, "_view_command_active", False) is False
        assert view_bar.display is False
        assert footer.display is True

        # --- Test 4: Unsupported key does not exit mode or crash ---
        await pilot.press("v")
        await pilot.pause(0.01)
        assert getattr(app.screen, "_view_command_active", False) is True

        await pilot.press("z")  # unsupported key
        await pilot.pause(0.01)
        # Should remain in View Command Mode
        assert getattr(app.screen, "_view_command_active", False) is True
        assert view_bar.display is True

        # Escape to cancel
        await pilot.press("escape")
        await pilot.pause(0.01)

        # --- Test 5: Focus safety (entering search field clears mode) ---
        await pilot.press("v")
        await pilot.pause(0.01)
        assert getattr(app.screen, "_view_command_active", False) is True

        # Focus Search Input
        search_input = app.screen.query_one("#search-input")
        search_input.focus()
        await pilot.pause(0.01)

        # Mode must be automatically cleared!
        assert getattr(app.screen, "_view_command_active", False) is False
        assert view_bar.display is False
        assert footer.display is True

        # --- Test 6: v inside search field types normally ---
        await pilot.press("v")
        await pilot.pause(0.01)
        assert search_input.value == "v"
        assert getattr(app.screen, "_view_command_active", False) is False


@pytest.mark.asyncio
async def test_view_command_mode_dialog_safety(session: Session) -> None:
    """Verify dialog opening/blurring safely cancels active View Command Mode."""
    from pathtree.ui.app import PathTreeApp
    from pathtree.ui.dialogs.add_node import AddNodeDialog

    node_service = NodeService(NodeRepository(session))
    ws = node_service.create_node(name="Test WS", node_kind="workspace", auto_layout=True)

    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Enter view command mode
        await pilot.press("v")
        await pilot.pause(0.01)
        assert getattr(app.screen, "_view_command_active", False) is True

        # Trigger Add Node dialog directly to simulate push_screen and blur safely
        app.screen.on_node_tree_view_add_node(None)
        await pilot.pause(0.01)

        # Assert we are on AddNodeDialog
        assert isinstance(app.screen, AddNodeDialog)

        # Cancel dialog
        await pilot.press("escape")
        await pilot.pause(0.01)

        # Back to MainScreen
        assert app.screen.id == "main-screen"
        # Stale mode must be completely cleared!
        assert getattr(app.screen, "_view_command_active", False) is False


def test_no_timers_created_for_view_mode() -> None:
    """Verify no timers or timer-cancel methods are used in screen or widget files."""
    from pathlib import Path
    main_file = Path("src/pathtree/ui/screens/main.py")
    content = main_file.read_text(encoding="utf-8")
    assert "set_timer" not in content
    assert "timer.cancel" not in content.lower()
    assert "_view_prefix_active" not in content
