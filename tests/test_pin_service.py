import uuid

import pytest
from sqlmodel import Session

from pathtree.database.repository import NodeRepository, PinRepository
from pathtree.models.node import Node
from pathtree.services.node_service import NodeService
from pathtree.services.pin_service import (
    DuplicatePinError,
    InvalidPositionError,
    NonexistentNodeError,
    PinService,
    StalePinReferenceError,
)


@pytest.fixture
def pin_service(session: Session) -> PinService:
    node_repo = NodeRepository(session)
    pin_repo = PinRepository(session)
    return PinService(node_repo, pin_repo)


@pytest.fixture
def node_service(session: Session) -> NodeService:
    node_repo = NodeRepository(session)
    return NodeService(node_repo)


def test_pin_node_success(session: Session, pin_service: PinService) -> None:
    # Create a workspace node
    node_repo = NodeRepository(session)
    node = node_repo.create(Node(name="My Workspace", node_kind="workspace"))

    # Pin the node
    pin = pin_service.pin_node(node.id, custom_label="Override Workspace")

    assert pin.id is not None
    assert pin.node_id == node.id
    assert pin.position == 1
    assert pin.custom_label == "Override Workspace"
    assert pin_service.is_pinned(node.id) is True


def test_pin_node_nonexistent(pin_service: PinService) -> None:
    fake_id = uuid.uuid4()
    with pytest.raises(NonexistentNodeError) as excinfo:
        pin_service.pin_node(fake_id)
    assert f"Node {fake_id} does not exist" in str(excinfo.value)


def test_pin_node_duplicate(session: Session, pin_service: PinService) -> None:
    node_repo = NodeRepository(session)
    node = node_repo.create(Node(name="My Folder", node_kind="workspace"))

    # Pin first time
    pin_service.pin_node(node.id)

    # Pin second time
    with pytest.raises(DuplicatePinError) as excinfo:
        pin_service.pin_node(node.id)
    assert f"Node {node.id} is already pinned" in str(excinfo.value)


def test_listing_and_deterministic_ordering(
    session: Session, pin_service: PinService
) -> None:
    node_repo = NodeRepository(session)
    n1 = node_repo.create(Node(name="Node A", node_kind="workspace"))
    n2 = node_repo.create(Node(name="Node B", node_kind="workspace"))
    n3 = node_repo.create(Node(name="Node C", node_kind="workspace"))

    pin_service.pin_node(n1.id)
    pin_service.pin_node(n2.id)
    pin_service.pin_node(n3.id)

    pins = pin_service.list_pins()
    assert len(pins) == 3
    assert pins[0].position == 1
    assert pins[1].position == 2
    assert pins[2].position == 3


def test_unpin_node_and_compacting(session: Session, pin_service: PinService) -> None:
    node_repo = NodeRepository(session)
    n1 = node_repo.create(Node(name="Node A", node_kind="workspace"))
    n2 = node_repo.create(Node(name="Node B", node_kind="workspace"))
    n3 = node_repo.create(Node(name="Node C", node_kind="workspace"))

    pin_service.pin_node(n1.id)
    pin_service.pin_node(n2.id)
    pin_service.pin_node(n3.id)

    # Unpin the second node
    pin_service.unpin_node(n2.id)

    pins = pin_service.list_pins()
    assert len(pins) == 2
    assert pins[0].node_id == n1.id
    assert pins[0].position == 1
    assert pins[1].node_id == n3.id
    assert pins[1].position == 2  # compacted!


def test_get_pin_by_position(session: Session, pin_service: PinService) -> None:
    node_repo = NodeRepository(session)
    node = node_repo.create(Node(name="My Node", node_kind="workspace"))
    pin_service.pin_node(node.id)

    # Valid position
    pin = pin_service.get_pin_by_position(1)
    assert pin.node_id == node.id

    # Invalid positions
    with pytest.raises(InvalidPositionError):
        pin_service.get_pin_by_position(0)

    with pytest.raises(InvalidPositionError):
        pin_service.get_pin_by_position(2)


def test_get_pin_stale_reference(session: Session, pin_service: PinService) -> None:
    from sqlmodel import text

    node_repo = NodeRepository(session)
    node = node_repo.create(Node(name="Temporary Node", node_kind="workspace"))
    pin_service.pin_node(node.id)

    # Bypass service and delete the node record directly from DB to
    # simulate a stale reference
    session.connection().execute(text("PRAGMA foreign_keys=OFF;"))
    node_repo.delete(node.id)
    session.connection().execute(text("PRAGMA foreign_keys=ON;"))

    with pytest.raises(StalePinReferenceError) as excinfo:
        pin_service.get_pin_by_position(1)
    assert "Pin references nonexistent node" in str(excinfo.value)


def test_reorder_pin(session: Session, pin_service: PinService) -> None:
    node_repo = NodeRepository(session)
    n1 = node_repo.create(Node(name="N1", node_kind="workspace"))
    n2 = node_repo.create(Node(name="N2", node_kind="workspace"))
    n3 = node_repo.create(Node(name="N3", node_kind="workspace"))

    p1 = pin_service.pin_node(n1.id)
    p2 = pin_service.pin_node(n2.id)
    p3 = pin_service.pin_node(n3.id)

    # Move p3 (position 3) to position 1
    pin_service.reorder_pin(p3.id, 1)

    pins = pin_service.list_pins()
    assert len(pins) == 3
    assert pins[0].id == p3.id
    assert pins[0].position == 1
    assert pins[1].id == p1.id
    assert pins[1].position == 2
    assert pins[2].id == p2.id
    assert pins[2].position == 3

    # Move p3 back to position 3
    pin_service.reorder_pin(p3.id, 3)
    pins = pin_service.list_pins()
    assert pins[0].id == p1.id
    assert pins[0].position == 1
    assert pins[1].id == p2.id
    assert pins[1].position == 2
    assert pins[2].id == p3.id
    assert pins[2].position == 3


def test_reorder_pin_invalid_position(
    session: Session, pin_service: PinService
) -> None:
    node_repo = NodeRepository(session)
    n1 = node_repo.create(Node(name="N1", node_kind="workspace"))
    p1 = pin_service.pin_node(n1.id)

    with pytest.raises(InvalidPositionError):
        pin_service.reorder_pin(p1.id, 0)

    with pytest.raises(InvalidPositionError):
        pin_service.reorder_pin(p1.id, 2)


def test_automatic_cleanup_on_node_delete(
    session: Session,
    node_service: NodeService,
    pin_service: PinService,
) -> None:
    # Create workspace and a child folder
    ws = node_service.create_node(name="My Workspace", node_kind="workspace")
    folder = node_service.create_node(
        name="My Folder", node_kind="folder", parent_id=ws.id
    )

    pin_service.pin_node(ws.id)
    pin_service.pin_node(folder.id)

    assert len(pin_service.list_pins()) == 2

    # Delete workspace (should recursively delete folder and cascade/cleanup pins)
    node_service.delete_node(ws.id, recursive=True)

    assert len(pin_service.list_pins()) == 0
