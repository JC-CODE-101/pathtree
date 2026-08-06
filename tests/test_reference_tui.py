"""Tests for the Resource Reference TUI integration."""

from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository, ResourceReferenceRepository
from pathtree.services.node_service import NodeService
from pathtree.services.resource_reference_service import ResourceReferenceService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.widgets.details import NodeDetailsPanel
from pathtree.ui.widgets.tree import NodeTreeView


@pytest.mark.asyncio
async def test_reference_tui_rendering_and_details(
    session: Session, tmp_path: Path
) -> None:
    """Verify that a reference node renders with ↗ and displays correct details."""
    repo = NodeRepository(session)
    ref_repo = ResourceReferenceRepository(session)
    node_service = NodeService(repo)
    ref_service = ResourceReferenceService(node_service, ref_repo)

    # Setup workspaces and resources using node_service
    ws = node_service.create_node(
        name="Main Workspace", node_kind="workspace", auto_layout=True
    )

    # Touch file so validation passes
    (tmp_path / "file.txt").touch()

    orig = node_service.create_node(
        name="My File",
        node_kind="resource",
        resource_type="file",
        path=str(tmp_path / "file.txt"),
        parent_id=ws.id,
        auto_route=True,
    )

    # Let's locate Custom group which was automatically created
    children = node_service.load_children(ws.id)
    custom_group = next(c for c in children if c.name == "Custom")

    # Create reference
    ref_service.create_reference(
        original_node_id=orig.id,
        destination_parent_id=custom_group.id,
        custom_name="My Referenced File",
    )

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)
        details = app.screen.query_one("#details-panel", NodeDetailsPanel)

        # 1. Expand Main Workspace
        await pilot.press("l")
        await pilot.pause(0.05)

        # 2. Go to System
        await pilot.press("j")
        await pilot.pause(0.05)

        # 3. Go to Custom
        await pilot.press("j")
        await pilot.pause(0.05)

        # 4. Expand Custom
        await pilot.press("l")
        await pilot.pause(0.05)

        # 5. Go to My Referenced File
        await pilot.press("j")
        await pilot.pause(0.05)

        # Check highlighted node is the reference node
        assert tree.cursor_node is not None
        ref_node = node_service.get_node(tree.cursor_node.data)
        assert ref_node is not None
        assert ref_node.resource_type == "reference"

        # Check rendering is decorated with ↗
        label = tree.cursor_node.label
        assert "↗" in label.plain

        # Check details panel contains active reference metadata
        content = details.render().plain
        assert "Reference Status: ACTIVE" in content
        assert "Original Name: My File" in content
        assert "Original Type: file" in content


@pytest.mark.asyncio
async def test_three_workspaces_tui_routing_and_protection(
    session: Session, tmp_path: Path
) -> None:
    """Verify three workspaces routing and system group TUI protection."""
    repo = NodeRepository(session)
    node_service = NodeService(repo)

    # 1. Create Workspace A, B and C programmatically
    ws_a = node_service.create_node(
        name="Workspace A", node_kind="workspace", auto_layout=True
    )
    ws_b = node_service.create_node(
        name="Workspace B", node_kind="workspace", auto_layout=True
    )
    ws_c = node_service.create_node(
        name="Workspace C", node_kind="workspace", auto_layout=True
    )

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # Let's locate Workspace C node in the tree and select it
        ws_c_tn = next(c for c in tree.root.children if c.data == ws_c.id)
        tree.move_cursor(ws_c_tn)
        await pilot.pause(0.05)

        # 2. Press 'a' to open Add Node Dialog for Workspace C context
        await pilot.press("a")
        await pilot.pause(0.05)

        from pathtree.ui.dialogs.add_node import AddNodeDialog

        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)
        # Ensure default resolved workspace ID is Workspace C
        assert dialog.workspace_id == ws_c.id

        # 3. Create a Folder from Workspace C
        await pilot.click("#radio-folder")
        dialog.query_one("#input-name").value = "Folder C"
        await pilot.click("#btn-create")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"

        # Assert Folder C was created and lands strictly inside Workspace C Custom
        folder_c = next(
            n for n in node_service.repository.list_all() if n.name == "Folder C"
        )
        ws_c_custom = node_service.get_custom_group(ws_c.id)
        assert folder_c.parent_id == ws_c_custom.id

        # Assert no folder was added to Workspace A or B
        ws_a_custom = node_service.get_custom_group(ws_a.id)
        ws_b_custom = node_service.get_custom_group(ws_b.id)
        assert len(node_service.load_children(ws_a_custom.id)) == 0
        assert len(node_service.load_children(ws_b_custom.id)) == 0

        # 4. Create a Script from Workspace C
        tree.move_cursor(ws_c_tn)
        await pilot.pause(0.05)
        await pilot.press("a")
        await pilot.pause(0.05)

        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)
        assert dialog.workspace_id == ws_c.id

        # Touch script file so validation passes
        (tmp_path / "script_c.py").touch()

        await pilot.click("#radio-script")
        dialog.query_one("#input-name").value = "Script C"
        dialog.query_one("#input-path").value = str(tmp_path / "script_c.py")
        await pilot.click("#btn-create")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"

        # Assert Script C lands strictly inside Workspace C System / Scripts
        script_c = next(
            n for n in node_service.repository.list_all() if n.name == "Script C"
        )
        ws_c_scripts = node_service.get_system_subsection(ws_c.id, "script")
        assert script_c.parent_id == ws_c_scripts.id

        # Assert no script was added to Workspace A or B
        ws_a_scripts = node_service.get_system_subsection(ws_a.id, "script")
        ws_b_scripts = node_service.get_system_subsection(ws_b.id, "script")
        assert len(node_service.load_children(ws_a_scripts.id)) == 0
        assert len(node_service.load_children(ws_b_scripts.id)) == 0

        # 5. Verify TUI-level protection of managed groups
        # Expand Workspace C first
        tree.move_cursor(ws_c_tn)
        await pilot.press("l")
        await pilot.pause(0.05)

        # Select System group
        await pilot.press("j")
        await pilot.pause(0.05)
        sys_node_id = tree.cursor_node.data
        sys_node = node_service.get_node(sys_node_id)
        assert sys_node.node_kind == "system_group"

        # Pressing 'e' must not open EditNodeDialog and instead notify
        await pilot.press("e")
        await pilot.pause(0.05)
        assert app.screen.id == "main-screen"  # No dialog opened

        # Pressing 'm' must not open MoveNodeDialog
        await pilot.press("m")
        await pilot.pause(0.05)
        assert app.screen.id == "main-screen"

        # Pressing 'd' must not open ConfirmDeleteDialog
        await pilot.press("d")
        await pilot.pause(0.05)
        assert app.screen.id == "main-screen"

        # Pressing 'o' must not open ActionMenu
        await pilot.press("o")
        await pilot.pause(0.05)
        assert app.screen.id == "main-screen"


@pytest.mark.asyncio
async def test_reference_creation_selection_focus_regression(
    session: Session, tmp_path: Path
) -> None:
    """Verify reference creation expands ancestors, selects it & retains focus."""
    from pathtree.database.repository import (
        LaunchProfileRepository,
        NodeRepository,
        ResourceReferenceRepository,
    )
    from pathtree.services.launch_profile_service import LaunchProfileService
    from pathtree.services.node_service import NodeService
    from pathtree.services.resource_reference_service import ResourceReferenceService
    from pathtree.ui.dialogs.action_menu import ResourceActionMenu
    from pathtree.ui.dialogs.reference_manager import ReferenceManagerDialog

    repo = NodeRepository(session)
    ref_repo = ResourceReferenceRepository(session)
    node_service = NodeService(repo)
    ref_service = ResourceReferenceService(node_service, ref_repo)
    lp_service = LaunchProfileService(node_service, LaunchProfileRepository(session))

    # create Workspace A and Workspace B
    ws_a = node_service.create_node(
        name="Workspace A", node_kind="workspace", auto_layout=True
    )
    ws_b = node_service.create_node(
        name="Workspace B", node_kind="workspace", auto_layout=True
    )

    # Touch file so validation passes
    (tmp_path / "script.py").touch()

    # create a real Launch Profile in Workspace A
    script_target = node_service.create_node(
        name="Target Script",
        node_kind="resource",
        resource_type="script",
        parent_id=ws_a.id,
        path=str(tmp_path / "script.py"),
    )

    profile = lp_service.create_profile(
        name="Blender Launcher",
        target_node_id=script_target.id,
        arguments=[],
    )
    profile_node_id = profile.profile_node_id

    # create nested folders in Workspace B / Custom
    custom_b = node_service.get_custom_group(ws_b.id)
    nested_fol1 = node_service.create_node(
        name="Outer Folder",
        node_kind="folder",
        parent_id=custom_b.id,
    )
    nested_fol2 = node_service.create_node(
        name="Inner Folder",
        node_kind="folder",
        parent_id=nested_fol1.id,
    )

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view", NodeTreeView)

        # 1. Select the Launch Profile node under Workspace A System / Launch Profiles
        # Let's expand Workspace A, and move cursor to Blender Launcher profile node
        ws_a_tn = next(c for c in tree.root.children if c.data == ws_a.id)
        tree.move_cursor(ws_a_tn)
        await pilot.press("l")  # Expand Workspace A
        await pilot.pause(0.05)

        # Expand System group
        await pilot.press("j")  # Move to System
        await pilot.press("l")  # Expand System
        await pilot.pause(0.05)

        # Move to Launch Profiles subsection
        # System has 7 subsections (Directories, Files, Scripts, etc.)
        # Blender Launcher is inside Launch Profiles
        for _ in range(6):
            await pilot.press("j")
        await pilot.press("l")  # Expand Launch Profiles
        await pilot.pause(0.05)

        await pilot.press("j")  # Move to Blender Launcher profile node
        await pilot.pause(0.05)
        assert tree.cursor_node.data == profile_node_id

        # 2. Press 'o' to open action menu
        await pilot.press("o")
        await pilot.pause(0.05)

        # We are on the action menu
        menu = app.screen
        assert isinstance(menu, ResourceActionMenu)

        # Select "Create Reference"
        options = [opt.id for opt in menu.actions]
        idx = options.index("create_reference")
        for _ in range(idx):
            await pilot.press("down")
        await pilot.press("enter")
        await pilot.pause(0.05)

        # Now the ReferenceManagerDialog is open
        dialog = app.screen
        assert isinstance(dialog, ReferenceManagerDialog)

        # Let's change destination workspace to Workspace B
        # Highlight and select select-workspace
        ws_select = dialog.query_one("#select-workspace")
        ws_select.value = ws_b.id
        await pilot.pause(0.05)

        # Select nested_fol2 as the destination folder
        fol_select = dialog.query_one("#select-folder")
        fol_select.value = nested_fol2.id
        await pilot.pause(0.05)

        # Click Create button
        await pilot.click("#btn-submit")
        await pilot.pause(0.05)

        # Back to main screen
        assert app.screen.id == "main-screen"

        # Assertions:
        # - assert the reference is selected after creation
        # - assert cursor_node.data equals the new reference node ID
        # - assert NodeTreeView has focus
        # - assert the destination ancestor chain remains expanded
        # - assert the cursor did not jump to Workspace A

        # Verify the new reference exists in DB
        all_refs = ref_service.repository.list_all()
        assert len(all_refs) == 1
        new_ref_rec = all_refs[0]
        new_ref_node_id = new_ref_rec.reference_node_id

        # 1. Focus check
        assert tree.has_focus is True

        # 2. Selection check
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == new_ref_node_id

        # 3. Destination ancestor chain expansion check
        # Outer Folder and Inner Folder must be expanded!
        nested_fol1_tree = (
            next(c for c in tree.root.children if c.data == ws_b.id)
            .children[1]
            .children[0]
        )
        assert nested_fol1_tree.is_expanded is True
        nested_fol2_tree = nested_fol1_tree.children[0]
        assert nested_fol2_tree.is_expanded is True
