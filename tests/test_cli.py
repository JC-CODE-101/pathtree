import uuid
from unittest.mock import patch

import pytest
from sqlmodel import Session

from pathtree.app import main
from pathtree.database.repository import NodeRepository, PinRepository
from pathtree.models.node import Node
from pathtree.services.pin_service import PinService


@pytest.fixture
def cli_session(session: Session):
    """Provide a database session specifically for CLI test context."""
    # We patch get_session so that when main() executes,
    # it uses our in-memory test session!
    with patch("pathtree.app.get_session") as mock_get_session:
        # Since we use `with get_session() as session:`, the mock context
        # manager should return our session.
        mock_get_session.return_value.__enter__.return_value = session
        yield session


def test_cli_empty_pin_list(cli_session, capsys) -> None:
    """Verify listing pins when no pins exist exits 0 and prints nothing."""
    with patch("sys.argv", ["pathtree", "--pins"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_cli_pin_and_list_pins(cli_session, capsys) -> None:
    """Verify that pinning a node and listing pins works via the CLI."""
    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="My Workspace", node_kind="workspace"))

    # Pin the workspace node
    with patch("sys.argv", ["pathtree", "--pin", str(ws.id)]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert 'Pinned "My Workspace" successfully' in captured.out

    # List pins
    with patch("sys.argv", ["pathtree", "-p"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    # Expected format: Position  Name/Label  Workspace
    assert "1  My Workspace       My Workspace" in captured.out


def test_cli_pin_invalid_uuid(cli_session, capsys) -> None:
    """Verify pinning with an invalid UUID fails with error and non-zero code."""
    with patch("sys.argv", ["pathtree", "--pin", "not-a-uuid"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "Error: Invalid UUID format" in captured.err


def test_cli_pin_missing_node(cli_session, capsys) -> None:
    """Verify pinning with a missing node UUID fails with error and non-zero code."""
    fake_id = str(uuid.uuid4())
    with patch("sys.argv", ["pathtree", "--pin", fake_id]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert f"Error: Node {fake_id} does not exist" in captured.err


def test_cli_pin_duplicate_rejection(cli_session, capsys) -> None:
    """Verify duplicate pin rejection via CLI."""
    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="My Workspace", node_kind="workspace"))

    # Pin once
    with patch("sys.argv", ["pathtree", "--pin", str(ws.id)]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    # Pin again (duplicate)
    with patch("sys.argv", ["pathtree", "--pin", str(ws.id)]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "is already pinned" in captured.err


def test_cli_unpin_and_compaction(cli_session, capsys) -> None:
    """Verify unpinning by visible position and positions compacting."""
    node_repo = NodeRepository(cli_session)
    n1 = node_repo.create(Node(name="Node A", node_kind="workspace"))
    n2 = node_repo.create(Node(name="Node B", node_kind="workspace"))

    pin_repo = PinRepository(cli_session)
    pin_service = PinService(node_repo, pin_repo)
    pin_service.pin_node(n1.id)
    pin_service.pin_node(n2.id)

    # Unpin first pin (position 1)
    with patch("sys.argv", ["pathtree", "--unpin", "1"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    # Check that remaining pin is compacted to position 1
    with patch("sys.argv", ["pathtree", "--pins"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "1  Node B             Node B" in captured.out


def test_cli_unpin_invalid_position(cli_session, capsys) -> None:
    """Verify unpinning with invalid position fails."""
    # Non-integer
    with patch("sys.argv", ["pathtree", "--unpin", "abc"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "Error: Invalid pin position" in captured.err

    # Out of range position
    with patch("sys.argv", ["pathtree", "--unpin", "99"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "No pin found at position 99" in captured.err


def test_cli_directory_numeric_activation(cli_session, tmp_path, capsys) -> None:
    """Verify numeric activation of directory resource outputs path."""
    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="My Workspace", node_kind="workspace"))
    folder = node_repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )

    pin_repo = PinRepository(cli_session)
    pin_service = PinService(node_repo, pin_repo)
    pin_service.pin_node(folder.id)

    # 1. Output to stdout (no --output file)
    with patch("sys.argv", ["pathtree", "-p", "1"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert str(tmp_path) in captured.out

    # 2. Output to --output file (preserve shell adapter behavior)
    out_file = tmp_path / "out_cli.txt"
    with patch("sys.argv", ["pathtree", "-p", "1", "--output", str(out_file)]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    assert out_file.exists()
    assert out_file.read_text(encoding="utf-8") == str(tmp_path)


def test_cli_non_directory_activation(cli_session, tmp_path, capsys) -> None:
    """Verify activation of non-directory resource executes default action."""
    # Let's test with a URL node
    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="My Workspace", node_kind="workspace"))
    url_node = node_repo.create(
        Node(
            name="My URL",
            node_kind="resource",
            resource_type="url",
            path="https://example.com",
            parent_id=ws.id,
        )
    )

    pin_repo = PinRepository(cli_session)
    pin_service = PinService(node_repo, pin_repo)
    pin_service.pin_node(url_node.id)

    # Mock open_url and copy_to_clipboard to avoid actual launching
    with patch("pathtree.utils.launcher.PlatformLauncher.open_url") as mock_open:
        with patch("sys.argv", ["pathtree", "-p", "1"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0

        mock_open.assert_called_once_with("https://example.com")


def test_cli_stale_reference_handling(cli_session, capsys) -> None:
    """Verify stale reference activation returns exit code 1."""
    from sqlmodel import text

    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="WS", node_kind="workspace"))

    pin_repo = PinRepository(cli_session)
    pin_service = PinService(node_repo, pin_repo)
    pin_service.pin_node(ws.id)

    # Delete WS with foreign_keys=OFF to bypass cascade deletion
    cli_session.connection().execute(text("PRAGMA foreign_keys=OFF;"))
    node_repo.delete(ws.id)
    cli_session.connection().execute(text("PRAGMA foreign_keys=ON;"))

    with patch("sys.argv", ["pathtree", "-p", "1"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert "Pin references nonexistent node" in captured.err
