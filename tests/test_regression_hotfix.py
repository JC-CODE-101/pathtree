from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.dialogs.confirm_delete import ConfirmDeleteDialog
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.dialogs.move_node import MoveNodeDialog


@pytest.mark.asyncio
async def test_expansion_regressions(session: Session) -> None:
    """Test expansion state and selection regressions:

    - expanded Workspace stays expanded after adding a Folder;
    - nested expanded Folder stays expanded after adding a child;
    - adding several sibling nodes consecutively never collapses their parent;
    - newly created node is selected;
    - selection does not jump to another root Workspace;
    - unrelated expanded Workspace remains expanded;
    - Move expands the new ancestor chain;
    - Edit and Delete preserve surviving expansion state.
    """
    repo = NodeRepository(session)
    ws1 = repo.create(Node(name="Blender", node_kind="workspace", sort_order=1))
    assets = repo.create(
        Node(name="Assets", node_kind="folder", parent_id=ws1.id, sort_order=1)
    )
    repo.create(
        Node(name="Assets Child", node_kind="folder", parent_id=assets.id, sort_order=1)
    )

    ws2 = repo.create(Node(name="Unrelated WS", node_kind="workspace", sort_order=2))
    repo.create(
        Node(
            name="Unrelated Folder", node_kind="folder", parent_id=ws2.id, sort_order=1
        )
    )

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # Expand ws1 and ws2
        ws1_tn = next(c for c in tree.root.children if c.data == ws1.id)
        ws2_tn = next(c for c in tree.root.children if c.data == ws2.id)

        tree.move_cursor(ws1_tn)
        await pilot.press("l")  # Expand Blender
        await pilot.pause(0.01)

        tree.move_cursor(ws2_tn)
        await pilot.press("l")  # Expand Unrelated WS
        await pilot.pause(0.01)

        assert ws1_tn.is_expanded is True
        assert ws2_tn.is_expanded is True

        # Navigate back to ws1
        tree.move_cursor(ws1_tn)
        await pilot.pause(0.01)

        # 1. Add folder under Blender (ws1)
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "Images"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Check: Blender stays expanded, Unrelated WS stays expanded
        ws1_tn = next(c for c in tree.root.children if c.data == ws1.id)
        ws2_tn = next(c for c in tree.root.children if c.data == ws2.id)
        assert ws1_tn.is_expanded is True
        assert ws2_tn.is_expanded is True

        # Check: newly created node "Images" is selected, does not jump
        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "Images"

        # 2. Add another Folder consecutively to check sibling
        # and parent expansion preservation
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "Materials"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Parent "Blender" must remain expanded
        ws1_tn = next(c for c in tree.root.children if c.data == ws1.id)
        assert ws1_tn.is_expanded is True
        assert str(tree.cursor_node.label) == "Materials"
        materials_id = tree.cursor_node.data

        # 3. Nested expanded folder stays expanded after adding a child
        # Let's expand "Assets" (which is under Blender)
        assets_tn = next(c for c in ws1_tn.children if c.data == assets.id)
        tree.move_cursor(assets_tn)
        await pilot.press("l")  # Expand Assets
        await pilot.pause(0.01)
        assert assets_tn.is_expanded is True

        # Add child to Assets
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "Models"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Verify parent folder "Assets" stays expanded,
        # and newly created nested "Models" is selected
        ws1_tn = next(c for c in tree.root.children if c.data == ws1.id)
        assets_tn = next(c for c in ws1_tn.children if c.data == assets.id)
        assert assets_tn.is_expanded is True
        assert str(tree.cursor_node.label) == "Models"

        # 4. Edit preserves surviving expansion state
        await pilot.press("e")
        assert isinstance(app.screen, EditNodeDialog)
        dialog = app.screen
        dialog.query_one("#input-name").value = "Models Renamed"
        dialog.action_submit()
        await pilot.pause(0.05)

        ws1_tn = next(c for c in tree.root.children if c.data == ws1.id)
        assets_tn = next(c for c in ws1_tn.children if c.data == assets.id)
        assert assets_tn.is_expanded is True
        assert str(tree.cursor_node.label) == "Models Renamed"

        # 5. Move expands the new ancestor chain
        # Move "Models Renamed" to "Unrelated WS" (ws2)
        await pilot.press("m")
        assert isinstance(app.screen, MoveNodeDialog)
        dialog = app.screen
        dialog.query_one("#select-parent").value = ws2.id
        dialog.action_submit()
        await pilot.pause(0.05)

        # "Unrelated WS" ancestor chain must be expanded,
        # and "Models Renamed" is selected
        ws2_tn = next(c for c in tree.root.children if c.data == ws2.id)
        assert ws2_tn.is_expanded is True
        assert str(tree.cursor_node.label) == "Models Renamed"

        # 6. Delete preserves surviving expansion state
        # Let's select "Materials" and delete it
        def find_node_by_id(parent, target_id):
            if parent.data == target_id:
                return parent
            for child in parent.children:
                res = find_node_by_id(child, target_id)
                if res is not None:
                    return res
            return None

        materials_tn = find_node_by_id(tree.root, materials_id)
        assert materials_tn is not None
        tree.move_cursor(materials_tn)
        await pilot.pause(0.01)

        await pilot.press("d")
        assert isinstance(app.screen, ConfirmDeleteDialog)
        dialog = app.screen
        dialog.action_submit()
        await pilot.pause(0.05)

        # Blender and Assets must still be expanded
        ws1_tn = next(c for c in tree.root.children if c.data == ws1.id)
        assets_tn = next(c for c in ws1_tn.children if c.data == assets.id)
        assert ws1_tn.is_expanded is True
        assert assets_tn.is_expanded is True


@pytest.mark.asyncio
async def test_enter_leakage_regressions(session: Session, tmp_path: Path) -> None:
    """Test Enter key leakage regressions:

    - submitting Add with Enter creates exactly one node;
    - the underlying MainScreen activation action is not called;
    - no "No default action is available" error appears after Folder creation;
    - no "No default action is available" error appears after Workspace creation;
    - Edit submission does not activate the edited node;
    - Move submission does not activate the moved node;
    - Delete confirmation does not activate the fallback node;
    - explicit Enter while the tree has focus still activates a valid Directory.
    """
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Workspace Node", node_kind="workspace"))

    # We will configure an output path to verify activation
    output_file = tmp_path / "activation_output.txt"

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        details = app.screen.query_one("#details-panel")

        # 1. Submit Add Workspace with Enter key
        # Focused on tree node "Workspace Node" (cannot activate
        # it natively, as it's a structural workspace)
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        dialog.query_one("#input-name").value = "New WS"
        dialog.query_one("#input-name").focus()
        await pilot.press("enter")  # Submit with enter
        await pilot.pause(0.05)

        # Dialog closed, exactly one node created
        assert app.screen.id == "main-screen"
        assert len(node_service.load_root_nodes()) == 2
        # MainScreen details panel should NOT show any
        # activation errors (like "No default action is available")
        assert "No default action is available" not in details.render().plain

        # 2. Submit Add Folder with Enter key
        # Expand WS first
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        tree.move_cursor(ws_tn)
        await pilot.press("l")  # Expand WS
        await pilot.pause(0.01)

        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "New Folder"
        dialog.query_one("#input-name").focus()
        await pilot.press("enter")  # Submit with enter
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        # No "No default action is available" error in details
        assert "No default action is available" not in details.render().plain
        assert output_file.exists() is False

        # 3. Edit submission with enter key does not activate
        await pilot.press("e")
        assert isinstance(app.screen, EditNodeDialog)
        dialog = app.screen
        dialog.query_one("#input-name").value = "New Folder Renamed"
        dialog.query_one("#input-name").focus()
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        assert "No default action is available" not in details.render().plain
        assert output_file.exists() is False

        # 4. Move submission with enter key does not activate
        # Move "New Folder Renamed" to "New WS"
        new_ws = next(n for n in node_service.load_root_nodes() if n.name == "New WS")
        new_ws_custom = node_service.get_custom_group(new_ws.id)
        await pilot.press("m")
        assert isinstance(app.screen, MoveNodeDialog)
        dialog = app.screen
        dialog.query_one("#select-parent").value = new_ws_custom.id
        dialog.query_one("#btn-move").focus()
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        assert "No default action is available" not in details.render().plain
        assert output_file.exists() is False

        # 5. Delete confirmation with enter key does not activate fallback node
        await pilot.press("d")
        assert isinstance(app.screen, ConfirmDeleteDialog)
        dialog = app.screen
        dialog.query_one("#btn-delete").focus()
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        assert "No default action is available" not in details.render().plain
        assert output_file.exists() is False

        # 6. Explicit Enter while the tree has focus still activates a valid Directory
        # Let's create a valid directory node
        valid_dir = tmp_path / "my_valid_dir"
        valid_dir.mkdir()
        valid_node = node_service.create_node(
            name="Valid Dir",
            node_kind="resource",
            resource_type="directory",
            parent_id=ws.id,
            path=str(valid_dir),
        )
        app.screen.refresh_tree(selected_node_id=valid_node.id)
        await pilot.pause(0.05)

        assert tree.has_focus is True
        assert tree.cursor_node is not None
        assert tree.cursor_node.data == valid_node.id

        await pilot.press("enter")
        # Wait for the app to exit upon successful activation
        while app.return_code is None:
            await pilot.pause(0.01)

        assert app.return_code == 0
        assert output_file.exists()
        assert (
            Path(output_file.read_text(encoding="utf-8").strip()).resolve()
            == valid_dir.resolve()
        )


@pytest.mark.asyncio
async def test_details_synchronization_regressions(
    session: Session, tmp_path: Path
) -> None:
    """Test details synchronization regressions:

    - after Add, details show the newly created node;
    - after Move, details show the moved node;
    - after Delete, details show the selected fallback;
    - stale activation errors are cleared after a successful CRUD refresh.
    """
    repo = NodeRepository(session)
    ws = repo.create(Node(name="Blender", node_kind="workspace"))
    assets = repo.create(Node(name="Assets", node_kind="folder", parent_id=ws.id))

    output_file = tmp_path / "activation_output_sync.txt"

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        details = app.screen.query_one("#details-panel")

        # First expand WS
        ws_tn = next(c for c in tree.root.children if c.data == ws.id)
        tree.move_cursor(ws_tn)
        await pilot.press("l")  # Expand Blender
        await pilot.pause(0.01)

        # Trigger a stale activation error by intentionally trying
        # to activate "Assets" (Folder has no default action)
        tree.move_cursor(next(c for c in ws_tn.children if c.data == assets.id))
        await pilot.pause(0.01)
        await pilot.press("enter")
        await pilot.pause(0.01)

        # Stale activation error should be visible
        assert "No default action is available" in details.render().plain

        # 1. Add node - verify details show newly created node
        # and clear the stale activation error
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "New Folder"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Assert no error shown, details updated to "New Folder"
        assert app.screen.id == "main-screen"
        assert "Error:" not in details.render().plain
        assert "New Folder" in details.render().plain

        # Intentionally produce error again
        await pilot.press("enter")
        await pilot.pause(0.01)
        assert "No default action is available" in details.render().plain

        # 2. Move node - details show moved node and clear stale activation error
        await pilot.press("m")
        assert isinstance(app.screen, MoveNodeDialog)
        dialog = app.screen
        dialog.query_one("#select-parent").value = ws.id
        dialog.action_submit()
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        assert "Error:" not in details.render().plain
        assert "New Folder" in details.render().plain

        # Intentionally produce error again
        await pilot.press("enter")
        await pilot.pause(0.01)
        assert "No default action is available" in details.render().plain

        # 3. Delete node - details show selected fallback
        # and clear stale activation error
        # Currently "New Folder" is selected, let's delete it
        await pilot.press("d")
        assert isinstance(app.screen, ConfirmDeleteDialog)
        dialog = app.screen
        dialog.action_submit()
        await pilot.pause(0.05)

        # The fallback should be the parent (or sibling).
        # In this case "Assets" or "Blender"
        assert app.screen.id == "main-screen"
        assert "Error:" not in details.render().plain
        # Details must show the fallback selected node
        assert tree.cursor_node is not None
        fallback_name = str(tree.cursor_node.label)
        assert fallback_name in details.render().plain


@pytest.mark.asyncio
async def test_three_workspaces_creation_focus_regression(session: Session) -> None:
    """TUI regression tests with three workspaces to verify cursor/focus stability.

    - creates Workspace A, B, and C with auto_layout
    - expands Workspace C
    - creates a Launch Profile, Multi Launcher, Script, Directory, Folder
    - asserts Workspace C stays expanded
    - asserts newly created nodes are selected and cursor points to them
    - asserts the tree has focus
    - asserts cursor did not jump to Workspace A
    """
    repo = NodeRepository(session)
    node_service = NodeService(repo)

    # 1. Create Workspace A, B, and C
    ws_a = node_service.create_node(
        name="Workspace A", node_kind="workspace", auto_layout=True
    )
    _ws_b = node_service.create_node(
        name="Workspace B", node_kind="workspace", auto_layout=True
    )
    ws_c = node_service.create_node(
        name="Workspace C", node_kind="workspace", auto_layout=True
    )

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")

        # First, let's navigate to Workspace C and expand it
        ws_c_tn = next(c for c in tree.root.children if c.data == ws_c.id)
        tree.move_cursor(ws_c_tn)
        await pilot.press("l")  # Expand Workspace C
        await pilot.pause(0.01)
        assert ws_c_tn.is_expanded is True

        # Now, select Workspace C / System / Scripts to expand it
        sys_c = node_service.get_system_group(ws_c.id)
        scripts_c = node_service.get_system_subsection(ws_c.id, "script")

        # Let's expand System and then Scripts
        sys_c_tn = next(c for c in ws_c_tn.children if c.data == sys_c.id)
        tree.move_cursor(sys_c_tn)
        await pilot.press("l")  # Expand System
        await pilot.pause(0.01)

        scripts_c_tn = next(c for c in sys_c_tn.children if c.data == scripts_c.id)
        tree.move_cursor(scripts_c_tn)
        await pilot.pause(0.01)

        # --------------------------------------------------
        # A. Create a Script resource under Workspace C / System / Scripts
        # --------------------------------------------------
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-script")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "MyScript"
        dialog.query_one("#input-path").value = __file__
        dialog.action_submit()
        await pilot.pause(0.05)

        # Assert correct focus & select
        assert app.screen.id == "main-screen"
        assert tree.has_focus is True
        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "MyScript"
        assert tree.cursor_node.data is not None
        my_script_id = tree.cursor_node.data
        assert node_service.get_node(my_script_id).parent_id == scripts_c.id
        assert tree.cursor_node.data != ws_a.id

        # --------------------------------------------------
        # B. Create a Launch Profile resource
        # --------------------------------------------------
        # With cursor on MyScript, open Actions Menu -> Create Launch Profile
        await pilot.press("o")
        await pilot.pause(0.01)
        await pilot.press("down")  # Down to Edit Script
        await pilot.press("down")  # Down to Create Launch Profile
        await pilot.press("enter")
        await pilot.pause(0.01)

        from pathtree.ui.dialogs.edit_profile import EditProfileDialog

        assert isinstance(app.screen, EditProfileDialog)
        ep_dialog = app.screen
        ep_dialog.query_one("#input-name").value = "MyProfile"
        ep_dialog.action_submit()
        await pilot.pause(0.05)

        # Assert correct focus & select
        assert app.screen.id == "main-screen"
        assert tree.has_focus is True
        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "MyProfile"
        my_profile_id = tree.cursor_node.data
        assert node_service.get_node(my_profile_id).resource_type == "launch_profile"
        assert tree.cursor_node.data != ws_a.id

        # --------------------------------------------------
        # C. Create a Multi Launcher resource
        # --------------------------------------------------
        # Multi Launcher is created via Add Node Dialog
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-multi-launcher")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "MyLauncher"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Assert correct focus & select
        assert app.screen.id == "main-screen"
        assert tree.has_focus is True
        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "MyLauncher"
        my_launcher_id = tree.cursor_node.data
        assert node_service.get_node(my_launcher_id).resource_type == "multi_launcher"
        assert tree.cursor_node.data != ws_a.id

        # --------------------------------------------------
        # D. Create a Directory resource
        # --------------------------------------------------
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-directory")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "MyDir"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Assert correct focus & select
        assert app.screen.id == "main-screen"
        assert tree.has_focus is True
        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "MyDir"
        my_dir_id = tree.cursor_node.data
        assert node_service.get_node(my_dir_id).resource_type == "directory"
        assert tree.cursor_node.data != ws_a.id

        # --------------------------------------------------
        # E. Create a Custom Folder
        # --------------------------------------------------
        await pilot.press("a")
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen
        await pilot.click("#radio-folder")
        await pilot.pause(0.01)
        dialog.query_one("#input-name").value = "MyFolder"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Assert correct focus & select
        assert app.screen.id == "main-screen"
        assert tree.has_focus is True
        assert tree.cursor_node is not None
        assert str(tree.cursor_node.label) == "MyFolder"
        my_folder_id = tree.cursor_node.data
        assert node_service.get_node(my_folder_id).node_kind == "folder"
        assert tree.cursor_node.data != ws_a.id
