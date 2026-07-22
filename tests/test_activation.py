import inspect
from pathlib import Path

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.ui.app import PathTreeApp
from pathtree.ui.screens.main import MainScreen


@pytest.mark.asyncio
async def test_enter_on_directory_preserves_output_file_behavior(
    session: Session, tmp_path: Path
) -> None:
    """Test that Enter on a Directory resource delegates to action framework.

    It writes the resolved path to the output file and exits successfully.
    """
    repo = NodeRepository(session)
    valid_dir = tmp_path / "valid_activation_dir"
    valid_dir.mkdir()
    repo.create(
        Node(
            name="Activate Me",
            path=str(valid_dir),
            sort_order=1,
            node_kind="resource",
            resource_type="directory",
        )
    )

    output_file = tmp_path / "output_select.txt"

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Press Enter on the highlighted Directory Node
        await pilot.press("enter")

        while app.return_code is None:
            await pilot.pause(0.01)

        assert output_file.exists()
        written_path = output_file.read_text(encoding="utf-8").strip()
        assert Path(written_path).resolve() == valid_dir.resolve()
        assert app.return_code == 0


@pytest.mark.asyncio
async def test_invalid_missing_paths_preserve_error_handling(
    session: Session, tmp_path: Path
) -> None:
    """Test that executing an invalid/missing path shows the error."""
    repo = NodeRepository(session)
    # Configure path to a nonexistent directory
    nonexistent = tmp_path / "does_not_exist"
    repo.create(
        Node(
            name="Missing Path Dir",
            path=str(nonexistent),
            sort_order=1,
            node_kind="resource",
            resource_type="directory",
        )
    )

    output_file = tmp_path / "output_select.txt"

    node_service = NodeService(repo)
    app = PathTreeApp(node_service=node_service, output=str(output_file))
    async with app.run_test() as pilot:
        while app.screen.id != "main-screen":
            await pilot.pause(0.01)
        await pilot.pause(0.01)

        # Press Enter on the Directory Node
        await pilot.press("enter")
        await pilot.pause(0.05)

        # App should not exit
        assert app.return_code is None
        assert not output_file.exists()

        # Error panel should be updated with the expected error message
        details = app.screen.query_one("#details-panel")
        assert "does not exist" in details.render().plain


@pytest.mark.asyncio
async def test_mainscreen_no_directory_specific_branching() -> None:
    """Verify MainScreen has no type-specific branching in activate_node."""
    source = inspect.getsource(MainScreen.activate_node)

    # MainScreen should delegate to action_registry and providers rather than
    # checking 'directory' or executing directory-specific operations directly.
    assert "resource_type == 'directory'" not in source
    assert "node.resource_type == 'directory'" not in source
    assert "directory" not in source.lower()

    # Verify delegation is done via the action_registry
    assert "self.action_registry.get_provider" in source
    assert "provider.execute" in source
