import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository, PinRepository
from pathtree.services.node_service import NodeService
from pathtree.services.pin_service import PinService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.dialogs.action_menu import ResourceActionMenu
from pathtree.ui.screens.pins import PinsScreen


@pytest.fixture
def tui_services(session: Session):
    node_repo = NodeRepository(session)
    pin_repo = PinRepository(session)
    node_service = NodeService(node_repo)
    pin_service = PinService(node_repo, pin_repo)
    return node_service, pin_service


@pytest.mark.asyncio
async def test_pins_tui_pin_unpin_action_menu(session: Session, tui_services) -> None:
    """Verify that pinning/unpinning a node via Action Menu works."""
    node_service, pin_service = tui_services

    # Create workspace node
    ws = node_service.create_node(name="Pin Workspace", node_kind="workspace")

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # 1. Open action menu on the workspace node
        await pilot.press("O")
        await pilot.pause(0.05)
        assert isinstance(app.screen, ResourceActionMenu)

        # Highlight and select "Pin Node" (it's the only option for Workspace)
        await pilot.press("enter")
        await pilot.pause(0.05)

        # Verify it pinned successfully
        assert app.screen.id == "main-screen"
        assert pin_service.is_pinned(ws.id) is True

        # 2. Open action menu again and verify "Unpin Node" is displayed
        await pilot.press("O")
        await pilot.pause(0.05)
        assert isinstance(app.screen, ResourceActionMenu)

        # Select "Unpin Node"
        await pilot.press("enter")
        await pilot.pause(0.05)

        # Verify it unpinned successfully
        assert app.screen.id == "main-screen"
        assert pin_service.is_pinned(ws.id) is False


@pytest.mark.asyncio
async def test_pins_screen_display_navigation_reorder(
    session: Session, tui_services
) -> None:
    """Verify PinsScreen displays, shifts, and selects pins."""
    node_service, pin_service = tui_services

    ws = node_service.create_node(name="Work A", node_kind="workspace")
    fol = node_service.create_node(name="Folder B", node_kind="folder", parent_id=ws.id)

    # Pin both nodes
    pin_service.pin_node(ws.id, custom_label="Custom WS")
    pin_service.pin_node(fol.id)

    app = PathTreeApp(node_service=node_service)
    async with app.run_test(size=(80, 60)) as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)

        # Open Pins Screen with 'p'
        await pilot.press("p")
        await pilot.pause(0.05)

        assert isinstance(app.screen, PinsScreen)
        pins_screen = app.screen

        # Verify pins displayed
        assert len(pins_screen._row_node_ids) == 2
        assert pins_screen._row_node_ids[0] == ws.id
        assert pins_screen._row_node_ids[1] == fol.id

        # 1. Test reordering: move ws (row 0) down
        # Pins initially: [ws, fol]
        # Pressing ']' moves current highlighted row (0) down
        await pilot.press("]")
        await pilot.pause(0.05)

        # Pins should now be: [fol, ws]
        pins = pin_service.list_pins()
        assert pins[0].node_id == fol.id
        assert pins[1].node_id == ws.id

        # 2. Test navigation/activation:
        # Press Enter on highlighted row to select/navigate to it
        # Pins screen should close and target node gets highlighted in main tree
        await pilot.press("enter")
        await pilot.pause(0.05)

        assert app.screen.id == "main-screen"
        tree = app.screen.query_one("#tree-view")
        assert tree.cursor_node is not None
        # Should have selected fol.id or ws.id depending on restored row focus
        # It's verified to close the screen and focus back to the tree
        assert tree.has_focus is True
