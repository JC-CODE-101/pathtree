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
        # Since we use `with get_session() as session:`,
        # the mock context manager should return our session.
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


def test_cli_structural_pins_hidden_from_listing(cli_session, capsys) -> None:
    """Verify Workspace and Folder pins are hidden from CLI listings."""
    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="WS", node_kind="workspace"))
    fol = node_repo.create(Node(name="Folder", node_kind="folder", parent_id=ws.id))
    directory = node_repo.create(
        Node(
            name="Dir Resource",
            node_kind="resource",
            resource_type="directory",
            path="/tmp/dir",
            parent_id=ws.id,
        )
    )

    pin_repo = PinRepository(cli_session)
    pin_service = PinService(node_repo, pin_repo)
    pin_service.pin_node(ws.id)
    pin_service.pin_node(fol.id)
    pin_service.pin_node(directory.id)

    # 1. Standard listing should ONLY list Directory pin with
    # compact numbering (position 1)
    with patch("sys.argv", ["pathtree", "-p"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert len(lines) == 1
    assert "1  Dir Resource" in lines[0]


def test_cli_compact_visible_numbering_activation_and_unpin(
    cli_session, tmp_path, capsys
) -> None:
    """Verify compact visible numbering, and unpin/activation resolving by it."""
    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="WS", node_kind="workspace"))
    fol = node_repo.create(Node(name="Folder", node_kind="folder", parent_id=ws.id))
    directory = node_repo.create(
        Node(
            name="My Dir",
            node_kind="resource",
            resource_type="directory",
            path=str(tmp_path),
            parent_id=ws.id,
        )
    )
    script_node = node_repo.create(
        Node(
            name="My Script",
            node_kind="resource",
            resource_type="script",
            path=__file__,
            parent_id=ws.id,
        )
    )

    pin_repo = PinRepository(cli_session)
    pin_service = PinService(node_repo, pin_repo)
    # Pin order:
    # 1. WS (structural, hidden)
    # 2. Directory (visible, compact CLI position 1)
    # 3. Folder (structural, hidden)
    # 4. Script (visible, compact CLI position 2)
    pin_service.pin_node(ws.id)
    pin_service.pin_node(directory.id)
    pin_service.pin_node(fol.id)
    pin_service.pin_node(script_node.id)

    # List pins -> should show 1: Directory, 2: Script
    with patch("sys.argv", ["pathtree", "-p"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "1  My Dir" in captured.out
    assert "2  My Script" in captured.out

    # Activate visible position 2 (script) -> runs action
    # Mock script launcher in terminal
    with patch(
        "pathtree.utils.launcher.PlatformLauncher.launch_in_terminal"
    ) as mock_launch:
        mock_launch.return_value.success = True
        with patch("sys.argv", ["pathtree", "-p", "2"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0

    # Unpin by visible position 1 (directory)
    with patch("sys.argv", ["pathtree", "--unpin", "1"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    # List pins again -> directory is gone, script compacted to position 1
    with patch("sys.argv", ["pathtree", "-p"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "1  My Script" in captured.out
    assert "My Dir" not in captured.out


def test_cli_value_outputs_without_execution(cli_session, capsys) -> None:
    """Verify --value extracts path/URL for all resource types without executing."""
    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="WS", node_kind="workspace"))

    directory = node_repo.create(
        Node(
            name="Dir",
            node_kind="resource",
            resource_type="directory",
            path="/tmp/dir",
            parent_id=ws.id,
        )
    )
    file_node = node_repo.create(
        Node(
            name="File",
            node_kind="resource",
            resource_type="file",
            path="/tmp/file.txt",
            parent_id=ws.id,
        )
    )
    script_node = node_repo.create(
        Node(
            name="Script",
            node_kind="resource",
            resource_type="script",
            path="/tmp/script.sh",
            parent_id=ws.id,
        )
    )
    exec_node = node_repo.create(
        Node(
            name="Executable",
            node_kind="resource",
            resource_type="executable",
            path="/tmp/bin.exe",
            parent_id=ws.id,
        )
    )
    url_node = node_repo.create(
        Node(
            name="URL",
            node_kind="resource",
            resource_type="url",
            path="https://example.com/pathtree",
            parent_id=ws.id,
        )
    )

    pin_repo = PinRepository(cli_session)
    pin_service = PinService(node_repo, pin_repo)
    pin_service.pin_node(directory.id)
    pin_service.pin_node(file_node.id)
    pin_service.pin_node(script_node.id)
    pin_service.pin_node(exec_node.id)
    pin_service.pin_node(url_node.id)

    # 1. Directory value
    with patch("sys.argv", ["pathtree", "-p", "1", "--value"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == "/tmp/dir"

    # 2. File value
    with patch("sys.argv", ["pathtree", "-p", "2", "--value"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == "/tmp/file.txt"

    # 3. Script value (verify it does NOT execute)
    with patch(
        "pathtree.utils.launcher.PlatformLauncher.launch_process"
    ) as mock_launch:
        with patch("sys.argv", ["pathtree", "-p", "3", "--value"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
        mock_launch.assert_not_called()
    assert capsys.readouterr().out.strip() == "/tmp/script.sh"

    # 4. Executable value (verify it does NOT launch)
    with patch(
        "pathtree.utils.launcher.PlatformLauncher.launch_process"
    ) as mock_launch:
        with patch("sys.argv", ["pathtree", "-p", "4", "--value"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
        mock_launch.assert_not_called()
    assert capsys.readouterr().out.strip() == "/tmp/bin.exe"

    # 5. URL value (verify it does NOT open default browser)
    with patch("pathtree.utils.launcher.PlatformLauncher.open_url") as mock_open:
        with patch("sys.argv", ["pathtree", "-p", "5", "--value"]):
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 0
        mock_open.assert_not_called()
    assert capsys.readouterr().out.strip() == "https://example.com/pathtree"


def test_cli_type_filters_and_values_output(cli_session, capsys) -> None:
    """Verify CLI filters and --values output."""
    node_repo = NodeRepository(cli_session)
    ws = node_repo.create(Node(name="WS", node_kind="workspace"))

    directory = node_repo.create(
        Node(
            name="Dir",
            node_kind="resource",
            resource_type="directory",
            path="/tmp/dir",
            parent_id=ws.id,
        )
    )
    script_node = node_repo.create(
        Node(
            name="Script",
            node_kind="resource",
            resource_type="script",
            path="/tmp/script.sh",
            parent_id=ws.id,
        )
    )

    pin_repo = PinRepository(cli_session)
    pin_service = PinService(node_repo, pin_repo)
    pin_service.pin_node(directory.id)
    pin_service.pin_node(script_node.id)

    # 1. Filter directories only
    with patch("sys.argv", ["pathtree", "-p", "--directories"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "1  Dir" in captured.out
    assert "Script" not in captured.out

    # 2. Filter scripts only
    with patch("sys.argv", ["pathtree", "-p", "--scripts"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "1  Script" in captured.out
    assert "Dir" not in captured.out

    # 3. Filter directories and output raw values
    with patch("sys.argv", ["pathtree", "-p", "--directories", "--values"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert captured.out.strip() == "/tmp/dir"


def test_cli_invalid_position_exits_nonzero(cli_session, capsys) -> None:
    """Verify that activating invalid visible position prints to stderr."""
    # List is empty, so position 1 is invalid
    with patch("sys.argv", ["pathtree", "-p", "1"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "Error: No pin found at position 1" in captured.err
