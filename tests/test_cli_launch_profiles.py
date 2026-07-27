from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session

from pathtree.app import main
from pathtree.database.repository import LaunchProfileRepository, NodeRepository
from pathtree.models.node import Node
from pathtree.services.launch_profile_service import LaunchProfileService


@pytest.fixture
def cli_session(session: Session):
    """Provide a database session specifically for CLI test context."""
    with patch("pathtree.app.get_session") as mock_get_session:
        mock_get_session.return_value.__enter__.return_value = session
        yield session


def test_cli_empty_profiles_list(cli_session, capsys) -> None:
    """Verify listing profiles when none exist exits 0 and prints nothing."""
    with patch("sys.argv", ["pathtree", "--profiles"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_cli_profiles_listing(cli_session, capsys) -> None:
    """Verify listing active and detached profiles."""
    from pathtree.services.node_service import NodeService

    node_repo = NodeRepository(cli_session)
    lp_repo = LaunchProfileRepository(cli_session)
    lp_service = LaunchProfileService(NodeService(node_repo), lp_repo)

    ws = node_repo.create(Node(name="Workspace X", node_kind="workspace"))
    script_node = node_repo.create(
        Node(
            name="My Script",
            node_kind="resource",
            resource_type="script",
            parent_id=ws.id,
            path=__file__,
        )
    )
    script_node2 = node_repo.create(
        Node(
            name="My Script 2",
            node_kind="resource",
            resource_type="script",
            parent_id=ws.id,
            path=__file__,
        )
    )

    # 1. Active profile
    lp_service.create_profile(
        name="Blender Normal",
        target_node_id=script_node.id,
        arguments=["--normal"],
    )

    # 2. Detached profile
    lp_service.create_profile(
        name="Blender Detached",
        target_node_id=script_node2.id,
        arguments=["--debug"],
    )

    from pathtree.services.node_service import NodeService

    node_service = NodeService(node_repo)
    node_service.delete_node(script_node2.id)

    # Run CLI --profiles
    with patch("sys.argv", ["pathtree", "--profiles"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    lines = captured.out.strip().splitlines()
    assert len(lines) == 2

    # Check headers / column alignments: Pos, Name, Workspace, Target, Type, Status
    assert "1" in lines[0]
    assert "Blender Normal" in lines[0]
    assert "Workspace X" in lines[0]
    assert "script" in lines[0]
    assert "active" in lines[0]

    assert "2" in lines[1]
    assert "Blender Detached" in lines[1]
    assert "detached" in lines[1]


@patch("pathtree.utils.launcher.PlatformLauncher.launch_process")
def test_cli_run_active_profile(mock_launch, cli_session, capsys) -> None:
    mock_launch.return_value = MagicMock(success=True, pid=456)

    from pathtree.services.node_service import NodeService

    node_repo = NodeRepository(cli_session)
    lp_repo = LaunchProfileRepository(cli_session)
    lp_service = LaunchProfileService(NodeService(node_repo), lp_repo)

    ws = node_repo.create(Node(name="Workspace X", node_kind="workspace"))
    script_node = node_repo.create(
        Node(
            name="My Script",
            node_kind="resource",
            resource_type="script",
            parent_id=ws.id,
            path=__file__,
        )
    )

    lp_service.create_profile(
        name="Blender Run",
        target_node_id=script_node.id,
        arguments=["--play"],
    )

    # Run profile position 1
    with patch("sys.argv", ["pathtree", "--profile", "1"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    captured = capsys.readouterr()
    assert "Launched profile: Blender Run" in captured.out
    assert captured.err == ""


def test_cli_run_detached_profile_rejection(cli_session, capsys) -> None:
    from pathtree.services.node_service import NodeService

    node_repo = NodeRepository(cli_session)
    lp_repo = LaunchProfileRepository(cli_session)
    lp_service = LaunchProfileService(NodeService(node_repo), lp_repo)

    ws = node_repo.create(Node(name="Workspace X", node_kind="workspace"))
    script_node = node_repo.create(
        Node(
            name="My Script",
            node_kind="resource",
            resource_type="script",
            parent_id=ws.id,
            path=__file__,
        )
    )

    lp_service.create_profile(
        name="Blender Detached Run",
        target_node_id=script_node.id,
        arguments=[],
    )

    # Detach it
    from pathtree.services.node_service import NodeService

    node_service = NodeService(node_repo)
    node_service.delete_node(script_node.id)

    # Run profile position 1 (which is detached)
    with patch("sys.argv", ["pathtree", "--profile", "1"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert 'Error: Launch Profile "Blender Detached Run" is detached.' in captured.err
    assert "Reconnect a compatible executable before running it." in captured.err


def test_cli_invalid_position_rejected(cli_session, capsys) -> None:
    with patch("sys.argv", ["pathtree", "--profile", "99"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert (
        "Error: Invalid profile position 99. No profile found at that position."
        in captured.err
    )


@patch("pathtree.services.launch_profile_service.LaunchProfileService.execute_profile")
def test_cli_terminal_mode_override_here(mock_execute, cli_session, capsys) -> None:
    from unittest import mock

    from pathtree.services.node_service import NodeService

    mock_execute.return_value = MagicMock(success=True, pid=456)

    node_repo = NodeRepository(cli_session)
    lp_repo = LaunchProfileRepository(cli_session)
    lp_service = LaunchProfileService(NodeService(node_repo), lp_repo)

    ws = node_repo.create(Node(name="Workspace X", node_kind="workspace"))
    script_node = node_repo.create(
        Node(
            name="My Script",
            node_kind="resource",
            resource_type="script",
            parent_id=ws.id,
            path=__file__,
        )
    )

    lp_service.create_profile(
        name="Blender Run",
        target_node_id=script_node.id,
        arguments=["--play"],
    )

    # Run profile position 1 with --here
    with patch("sys.argv", ["pathtree", "--profile", "1", "--here"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    mock_execute.assert_called_once_with(mock.ANY, terminal_mode_override="inherit")


@patch("pathtree.services.launch_profile_service.LaunchProfileService.execute_profile")
def test_cli_terminal_mode_override_new_terminal(
    mock_execute, cli_session, capsys
) -> None:
    from unittest import mock

    from pathtree.services.node_service import NodeService

    mock_execute.return_value = MagicMock(success=True, pid=456)

    node_repo = NodeRepository(cli_session)
    lp_repo = LaunchProfileRepository(cli_session)
    lp_service = LaunchProfileService(NodeService(node_repo), lp_repo)

    ws = node_repo.create(Node(name="Workspace X", node_kind="workspace"))
    script_node = node_repo.create(
        Node(
            name="My Script",
            node_kind="resource",
            resource_type="script",
            parent_id=ws.id,
            path=__file__,
        )
    )

    lp_service.create_profile(
        name="Blender Run",
        target_node_id=script_node.id,
        arguments=["--play"],
    )

    # Run profile position 1 with --new-terminal
    with patch("sys.argv", ["pathtree", "--profile", "1", "--new-terminal"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 0

    mock_execute.assert_called_once_with(
        mock.ANY, terminal_mode_override="new_terminal"
    )


def test_cli_terminal_mode_override_mutually_exclusive(cli_session, capsys) -> None:
    # Reject passing both overrides simultaneously
    with patch("sys.argv", ["pathtree", "--profile", "1", "--here", "--new-terminal"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 2

    captured = capsys.readouterr()
    assert "not allowed with argument" in captured.err


def test_cli_terminal_mode_override_no_profile_here(cli_session, capsys) -> None:
    # Reject passing --here without --profile
    with patch("sys.argv", ["pathtree", "--here"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 2

    captured = capsys.readouterr()
    assert "only allowed with --profile" in captured.err


def test_cli_terminal_mode_override_no_profile_new_terminal(
    cli_session, capsys
) -> None:
    # Reject passing --new-terminal without --profile
    with patch("sys.argv", ["pathtree", "--new-terminal"]):
        with pytest.raises(SystemExit) as excinfo:
            main()
        assert excinfo.value.code == 2

    captured = capsys.readouterr()
    assert "only allowed with --profile" in captured.err
