"""Unit and TUI integration tests for default node icons and the IconPicker."""

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.add_node import AddNodeDialog
from pathtree.ui.dialogs.edit_node import EditNodeDialog
from pathtree.ui.widgets.icon_picker import IconPicker
from pathtree.utils.icons import NodeIconCatalog


def test_node_icon_catalog_resolution() -> None:
    """1. Test that each node/resource type resolves to correct default."""
    catalog = NodeIconCatalog()

    # Workspace
    assert catalog.get_default_icon("workspace", None) == "◆"
    # Folder
    assert catalog.get_default_icon("folder", None) == "▸"
    # Directory Resource
    assert catalog.get_default_icon("resource", "directory") == "▪"
    # File Resource
    assert catalog.get_default_icon("resource", "file") == "▤"
    # Script Resource
    assert catalog.get_default_icon("resource", "script") == "⚡"
    # Executable Resource
    assert catalog.get_default_icon("resource", "executable") == "⚙"
    # URL Resource
    assert catalog.get_default_icon("resource", "url") == "↗"

    # Test safe fallback for unknown category
    assert catalog.get_default_icon("resource", "unknown_type") == "▪"


def test_node_icon_catalog_recommended_icons() -> None:
    """3. Test that the catalog lists recommended icons for current type."""
    catalog = NodeIconCatalog()

    # Workspace
    workspace_recs = catalog.get_recommended_icons("workspace", None)
    assert len(workspace_recs) == 4
    assert workspace_recs[0].symbol == "◆"
    assert workspace_recs[1].symbol == "◇"

    # Script
    script_recs = catalog.get_recommended_icons("resource", "script")
    assert any(rec.symbol == "⚡" for rec in script_recs)
    assert any(rec.symbol == "⌁" for rec in script_recs)


@pytest.mark.asyncio
async def test_newly_created_node_default_icon(session: Session) -> None:
    """2. Test that newly created nodes receive correct default icon."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # Trigger Add Node Dialog
        await pilot.press("a")
        await pilot.pause(0.05)
        assert isinstance(app.screen, AddNodeDialog)
        dialog = app.screen

        # Workspace type is selected by default. Name and submit.
        dialog.query_one("#input-name").value = "New WS"

        # The icon input should already have the default workspace icon "◆"
        icon_picker = dialog.query_one(IconPicker)
        assert icon_picker.value == "◆"

        dialog.action_submit()
        await pilot.pause(0.05)

        # Main screen returns and WS is created
        assert app.screen.id == "main-screen"
        nodes = node_service.load_root_nodes()
        assert len(nodes) == 1
        assert nodes[0].name == "New WS"
        assert nodes[0].icon == "◆"


@pytest.mark.asyncio
async def test_icon_picker_selection_persistence(session: Session) -> None:
    """4. Test that selecting an icon from the picker persists it correctly."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        await pilot.press("a")
        await pilot.pause(0.05)
        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)

        dialog.query_one("#input-name").value = "WS with Custom Icon"

        # Focus the IconPicker and accept the second option
        icon_picker = dialog.query_one(IconPicker)
        icon_picker.query_one(".icon-picker-input").focus()
        await pilot.pause(0.05)

        assert icon_picker.is_suggestions_visible is True
        # Choose alternative (◇ White Diamond)
        option_list = icon_picker.option_list
        # Index 0 is Default, index 1 is ◆ Diamond, index 2 is ◇ White Diamond
        option_list.highlighted = 2
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert icon_picker.value == "◇"
        dialog.action_submit()
        await pilot.pause(0.05)

        # Verify it was saved with '◇'
        nodes = node_service.load_root_nodes()
        assert nodes[0].icon == "◇"


@pytest.mark.asyncio
async def test_edit_node_custom_and_default_icons(session: Session) -> None:
    """5. Test custom icons preservation, 6. Default restore."""
    repo = NodeRepository(session)
    # Pre-populate with custom icon '◇'
    node = repo.create(Node(name="Custom WS", node_kind="workspace", icon="◇"))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # Open Edit Dialog
        await pilot.press("e")
        await pilot.pause(0.05)
        dialog = app.screen
        assert isinstance(dialog, EditNodeDialog)

        icon_picker = dialog.query_one(IconPicker)
        assert icon_picker.value == "◇"

        # 5. Preserving Custom Icon: Submit without changes preserves it
        dialog.action_submit()
        await pilot.pause(0.05)
        assert node_service.get_node(node.id).icon == "◇"

        # Open Edit Dialog again to test Resetting to Default
        await pilot.press("e")
        await pilot.pause(0.05)
        dialog = app.screen
        assert isinstance(dialog, EditNodeDialog)

        icon_picker = dialog.query_one(IconPicker)
        icon_picker.query_one(".icon-picker-input").focus()
        await pilot.pause(0.05)

        # Select the 'Default' option (index 0)
        icon_picker.option_list.highlighted = 0
        await pilot.press("enter")
        await pilot.pause(0.05)

        # Should revert to default '◆'
        assert icon_picker.value == "◆"

        dialog.action_submit()
        await pilot.pause(0.05)
        assert node_service.get_node(node.id).icon == "◆"


@pytest.mark.asyncio
async def test_changing_node_type_suggests_default(session: Session) -> None:
    """7. Test dynamic default suggestion on type change, 8. Preserve custom."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        await pilot.press("a")
        await pilot.pause(0.05)
        dialog = app.screen
        assert isinstance(dialog, AddNodeDialog)

        icon_picker = dialog.query_one(IconPicker)
        # 7. Untouched automatic default changes
        assert icon_picker.value == "◆"

        # Toggle to Folder
        await pilot.click("#radio-folder")
        await pilot.pause(0.05)
        # Should suggest default Folder icon '▸'
        assert icon_picker.value == "▸"

        # Toggle to Directory
        await pilot.click("#radio-directory")
        await pilot.pause(0.05)
        # Should suggest default Directory icon '▪'
        assert icon_picker.value == "▪"

        # Now explicitly enter a custom icon (type '★')
        icon_picker.value = "★"
        await pilot.pause(0.05)

        # 8. Changing type does NOT overwrite explicit custom icon
        await pilot.click("#radio-workspace")
        await pilot.pause(0.05)
        assert icon_picker.value == "★"

        await pilot.press("escape")


@pytest.mark.asyncio
async def test_existing_nodes_without_icons_rendering(session: Session) -> None:
    """9. Test existing nodes without icons display with fallback default."""
    repo = NodeRepository(session)
    # Create nodes with NO icon stored
    repo.create(Node(name="WS Legacy", node_kind="workspace", icon=None))

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        tree = app.screen.query_one("#tree-view")
        # Prepend fallback icon should be '◆ WS Legacy'
        node_label = tree.root.children[0].label
        assert node_label.plain == "◆ WS Legacy"
        # str representation should stay clean 'WS Legacy' for existing tests
        assert str(node_label) == "WS Legacy"


@pytest.mark.asyncio
async def test_dialogs_remain_keyboard_operable(session: Session) -> None:
    """11. Test that dialogs remain keyboard-operable, retaining escape etc."""
    node_service = NodeService(NodeRepository(session))
    app = PathTreeApp(node_service=node_service)
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # 11. Add dialog keyboard-operable
        await pilot.press("a")
        await pilot.pause(0.05)
        assert isinstance(app.screen, AddNodeDialog)

        # Escape closes it
        await pilot.press("escape")
        await pilot.pause(0.05)
        assert app.screen.id == "main-screen"
