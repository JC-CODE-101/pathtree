import pytest
from sqlmodel import Session

from pathtree.database.repository import (
    NodeRepository,
    ResourceReferenceRepository,
)
from pathtree.services.node_service import NodeService, ValidationError
from pathtree.services.resource_reference_service import (
    ResourceReferenceService,
)


@pytest.fixture(name="node_service")
def node_service_fixture(session: Session) -> NodeService:
    repo = NodeRepository(session)
    return NodeService(repo)


@pytest.fixture(name="ref_service")
def ref_service_fixture(
    session: Session, node_service: NodeService
) -> ResourceReferenceService:
    ref_repo = ResourceReferenceRepository(session)
    return ResourceReferenceService(node_service, ref_repo)


def test_workspace_layout_initialization(node_service: NodeService) -> None:
    """Test workspace creation layout initialization of System/Custom."""
    ws = node_service.create_node(
        name="AI Workspace", node_kind="workspace", auto_layout=True
    )
    assert ws.id is not None

    # Check that System and Custom are created under it
    children = node_service.load_children(ws.id)
    assert len(children) == 2
    system_group = next(c for c in children if c.name == "System")
    custom_group = next(c for c in children if c.name == "Custom")

    assert system_group.node_kind == "system_group"
    assert system_group.system_role == "system"
    assert custom_group.node_kind == "system_group"
    assert custom_group.system_role == "custom"

    # Check System subsections
    subsections = node_service.load_children(system_group.id)
    assert len(subsections) == 7
    roles = {s.system_role for s in subsections}
    expected_roles = {
        "directories",
        "files",
        "scripts",
        "executables",
        "urls",
        "launch_profiles",
        "multi_launchers",
    }
    assert roles == expected_roles


def test_automatic_placement_real_resources(
    node_service: NodeService,
) -> None:
    """Test that real resources route to System subsections automatically."""
    ws = node_service.create_node(
        name="AI Workspace", node_kind="workspace", auto_layout=True
    )

    # Create directory resource
    dir_node = node_service.create_node(
        name="My Books",
        node_kind="resource",
        resource_type="directory",
        parent_id=ws.id,
        auto_route=True,
    )
    assert dir_node.parent_id != ws.id

    # The actual parent should be the 'Directories' system group under System
    parent_node = node_service.get_node(dir_node.parent_id)
    assert parent_node is not None
    assert parent_node.node_kind == "system_group"
    assert parent_node.system_role == "directories"

    # Create URL resource
    url_node = node_service.create_node(
        name="ChatGPT",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="https://chat.openai.com",
        auto_route=True,
    )
    url_parent = node_service.get_node(url_node.parent_id)
    assert url_parent is not None
    assert url_parent.node_kind == "system_group"
    assert url_parent.system_role == "urls"


def test_automatic_placement_folders(node_service: NodeService) -> None:
    """Test that folder nodes route to Custom group automatically."""
    ws = node_service.create_node(
        name="AI Workspace", node_kind="workspace", auto_layout=True
    )

    folder_node = node_service.create_node(
        name="My Folder",
        node_kind="folder",
        parent_id=ws.id,
        auto_route=True,
    )
    assert folder_node.parent_id != ws.id

    parent_node = node_service.get_node(folder_node.parent_id)
    assert parent_node is not None
    assert parent_node.node_kind == "system_group"
    assert parent_node.system_role == "custom"


def test_prevent_manual_creation_in_system(
    node_service: NodeService,
) -> None:
    """Test that folders and references cannot be created in System area."""
    ws = node_service.create_node(
        name="AI Workspace", node_kind="workspace", auto_layout=True
    )
    children = node_service.load_children(ws.id)
    system_group = next(c for c in children if c.name == "System")

    # Try creating folder inside System
    with pytest.raises(ValidationError) as exc:
        node_service.create_node(
            name="Illegal Folder",
            node_kind="folder",
            parent_id=system_group.id,
        )
    assert "cannot be created inside the System area" in str(exc.value)

    # Try creating reference inside System
    with pytest.raises(ValidationError) as exc:
        node_service.create_node(
            name="Illegal Ref",
            node_kind="resource",
            resource_type="reference",
            parent_id=system_group.id,
        )
    assert "cannot be created inside the System area" in str(exc.value)


def test_create_reference_and_retrieval(
    node_service: NodeService, ref_service: ResourceReferenceService
) -> None:
    """Test creating a reference and retrieving its properties."""
    ws = node_service.create_node(
        name="AI Workspace", node_kind="workspace", auto_layout=True
    )
    custom_group = next(
        c for c in node_service.load_children(ws.id) if c.name == "Custom"
    )

    # Create original URL
    orig = node_service.create_node(
        name="ChatGPT",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="https://chat.openai.com",
        auto_route=True,
    )

    # Create reference in Custom
    ref = ref_service.create_reference(
        original_node_id=orig.id,
        destination_parent_id=custom_group.id,
        custom_name="My ChatGPT",
    )

    assert ref.id is not None
    ref_node = node_service.get_node(ref.reference_node_id)
    assert ref_node is not None
    assert ref_node.name == "My ChatGPT"
    assert ref_node.node_kind == "resource"
    assert ref_node.resource_type == "reference"

    # Retrieve original
    orig_fetched = ref_service.get_original_node(ref_node.id)
    assert orig_fetched is not None
    assert orig_fetched.id == orig.id
    assert ref_service.is_broken(ref_node.id) is False


def test_cross_workspace_references(
    node_service: NodeService, ref_service: ResourceReferenceService
) -> None:
    """Test references pointing to resources in a different workspace."""
    ws1 = node_service.create_node(
        name="Workspace 1", node_kind="workspace", auto_layout=True
    )
    ws2 = node_service.create_node(
        name="Workspace 2", node_kind="workspace", auto_layout=True
    )
    custom_ws2 = next(
        c for c in node_service.load_children(ws2.id) if c.name == "Custom"
    )

    # Create original in ws1
    orig = node_service.create_node(
        name="Workspace 1 Doc",
        node_kind="resource",
        resource_type="url",
        parent_id=ws1.id,
        path="https://workspace1.com",
        auto_route=True,
    )

    # Create reference in ws2 pointing to ws1
    ref = ref_service.create_reference(
        original_node_id=orig.id,
        destination_parent_id=custom_ws2.id,
    )

    ref_node = node_service.get_node(ref.reference_node_id)
    assert ref_node.name == "Workspace 1 Doc"
    assert ref_service.get_original_node(ref_node.id).id == orig.id


def test_broken_references_and_reconnection(
    node_service: NodeService, ref_service: ResourceReferenceService
) -> None:
    """Test reference broken state and reconnection logic."""
    ws = node_service.create_node(
        name="Workspace", node_kind="workspace", auto_layout=True
    )
    custom_group = next(
        c for c in node_service.load_children(ws.id) if c.name == "Custom"
    )

    orig1 = node_service.create_node(
        name="Doc 1",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="https://doc1.com",
        auto_route=True,
    )
    orig2 = node_service.create_node(
        name="Doc 2",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="https://doc2.com",
        auto_route=True,
    )

    ref = ref_service.create_reference(orig1.id, custom_group.id)
    ref_node_id = ref.reference_node_id

    assert ref_service.is_broken(ref_node_id) is False

    # Delete orig1
    node_service.delete_node(orig1.id)

    # Reference should now be broken but NOT deleted!
    assert ref_service.is_broken(ref_node_id) is True
    assert node_service.get_node(ref_node_id) is not None

    # Reconnect to orig2
    ref_service.reconnect_reference(ref_node_id, orig2.id)
    assert ref_service.is_broken(ref_node_id) is False
    assert ref_service.get_original_node(ref_node_id).id == orig2.id


def test_duplicate_reference(
    node_service: NodeService, ref_service: ResourceReferenceService
) -> None:
    """Test duplicating a reference node."""
    ws = node_service.create_node(
        name="Workspace", node_kind="workspace", auto_layout=True
    )
    custom_group = next(
        c for c in node_service.load_children(ws.id) if c.name == "Custom"
    )

    orig = node_service.create_node(
        name="Doc",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="https://doc.com",
        auto_route=True,
    )

    ref = ref_service.create_reference(orig.id, custom_group.id)
    dup_node = ref_service.duplicate_reference(ref.reference_node_id)

    assert dup_node.id != ref.reference_node_id
    assert dup_node.name == "Doc Copy"
    assert ref_service.get_original_node(dup_node.id).id == orig.id


def test_delete_reference_does_not_delete_original(
    node_service: NodeService, ref_service: ResourceReferenceService
) -> None:
    """Test that deleting a reference never deletes the original resource."""
    ws = node_service.create_node(
        name="Workspace", node_kind="workspace", auto_layout=True
    )
    custom_group = next(
        c for c in node_service.load_children(ws.id) if c.name == "Custom"
    )

    orig = node_service.create_node(
        name="Doc",
        node_kind="resource",
        resource_type="url",
        parent_id=ws.id,
        path="https://doc.com",
        auto_route=True,
    )

    ref = ref_service.create_reference(orig.id, custom_group.id)
    ref_node_id = ref.reference_node_id

    # Delete reference
    ref_service.delete_reference(ref_node_id)

    # Reference node should be gone
    assert node_service.get_node(ref_node_id) is None
    # Original node must STILL exist!
    assert node_service.get_node(orig.id) is not None


def test_centralized_hierarchy_rules(node_service: NodeService) -> None:
    """Verify hierarchy selection rules from get_valid_parent_choices."""
    ws = node_service.create_node(name="WS", node_kind="workspace", auto_layout=True)
    custom_group = next(
        c for c in node_service.load_children(ws.id) if c.name == "Custom"
    )
    system_group = next(
        c for c in node_service.load_children(ws.id) if c.name == "System"
    )

    folder1 = node_service.create_node(
        name="Folder1", node_kind="folder", parent_id=custom_group.id
    )

    # 1. Folder parent choices should only contain Custom group and sub-folders
    folder_choices = node_service.get_valid_parent_choices("folder")
    folder_choice_ids = {val_id for _, val_id in folder_choices}
    assert custom_group.id in folder_choice_ids
    assert folder1.id in folder_choice_ids
    assert system_group.id not in folder_choice_ids

    # 2. Workspace parent choices should only contain Root (None)
    ws_choices = node_service.get_valid_parent_choices("workspace")
    assert ws_choices == [("Root", None)]

    # 3. Real resource choices should contain Workspace nodes
    res_choices = node_service.get_valid_parent_choices("resource", "file")
    res_choice_ids = {val_id for _, val_id in res_choices}
    assert ws.id in res_choice_ids


def test_move_node_routing_and_protection(node_service: NodeService) -> None:
    """Verify that moves adhere to strict parent constraints."""
    ws1 = node_service.create_node(name="WS1", node_kind="workspace", auto_layout=True)
    ws2 = node_service.create_node(name="WS2", node_kind="workspace", auto_layout=True)
    custom_group = next(
        c for c in node_service.load_children(ws1.id) if c.name == "Custom"
    )
    system_group = next(
        c for c in node_service.load_children(ws1.id) if c.name == "System"
    )

    folder = node_service.create_node(
        name="My Folder", node_kind="folder", parent_id=custom_group.id
    )

    # Managed system groups cannot be moved
    with pytest.raises(ValidationError, match="Managed system groups cannot be moved"):
        node_service.move_node(system_group.id, ws2.id)

    # Folder cannot be moved to System area
    with pytest.raises(ValidationError, match="cannot be moved inside the System area"):
        node_service.move_node(folder.id, system_group.id)

    # Real resource is automatically routed on move
    orig = node_service.create_node(
        name="Doc",
        node_kind="resource",
        resource_type="url",
        parent_id=ws1.id,
        path="https://doc.com",
        auto_route=True,
    )
    moved = node_service.move_node(orig.id, ws2.id)
    # Parent of moved node should be the URLs system group of ws2
    ws2_system = next(
        c for c in node_service.load_children(ws2.id) if c.name == "System"
    )
    ws2_urls = next(
        c for c in node_service.load_children(ws2_system.id) if c.system_role == "urls"
    )
    assert moved.parent_id == ws2_urls.id


def test_current_parent_robustness_and_stale_uuids(
    node_service: NodeService,
) -> None:
    """Verify parent choices options load robustly with current fallback."""
    ws = node_service.create_node(name="WS", node_kind="workspace", auto_layout=True)
    system_group = next(
        c for c in node_service.load_children(ws.id) if c.name == "System"
    )
    dir_group = next(
        c
        for c in node_service.load_children(system_group.id)
        if c.system_role == "directories"
    )

    # If we request choices for folder with legacy parent_id
    choices = node_service.get_valid_parent_choices(
        node_kind="folder",
        current_parent_id=dir_group.id,
    )
    # The dir_group.id must be prepended robustly
    assert choices[0][1] == dir_group.id
    assert "Current:" in choices[0][0]


def test_multi_workspace_routing_accuracy(node_service: NodeService) -> None:
    """Verify that nodes land in the selected workspace only."""
    ws1 = node_service.create_node(name="WS1", node_kind="workspace", auto_layout=True)
    ws2 = node_service.create_node(name="WS2", node_kind="workspace", auto_layout=True)
    ws3 = node_service.create_node(name="WS3", node_kind="workspace", auto_layout=True)

    # 1. Create folder explicitly on WS2
    folder_ws2 = node_service.create_node(
        name="WS2 Folder",
        node_kind="folder",
        workspace_id=ws2.id,
    )
    ws2_custom = next(
        c for c in node_service.load_children(ws2.id) if c.name == "Custom"
    )
    assert folder_ws2.parent_id == ws2_custom.id

    # 2. Create URL explicitly on WS3
    url_ws3 = node_service.create_node(
        name="WS3 URL",
        node_kind="resource",
        resource_type="url",
        path="https://ws3.com",
        workspace_id=ws3.id,
    )
    ws3_sys = next(c for c in node_service.load_children(ws3.id) if c.name == "System")
    ws3_urls = next(
        c for c in node_service.load_children(ws3_sys.id) if c.system_role == "urls"
    )
    assert url_ws3.parent_id == ws3_urls.id

    # 3. Create script explicitly on WS1
    script_ws1 = node_service.create_node(
        name="WS1 Script",
        node_kind="resource",
        resource_type="script",
        path=__file__,  # must exist
        workspace_id=ws1.id,
    )
    ws1_sys = next(c for c in node_service.load_children(ws1.id) if c.name == "System")
    ws1_scripts = next(
        c for c in node_service.load_children(ws1_sys.id) if c.system_role == "scripts"
    )
    assert script_ws1.parent_id == ws1_scripts.id


def test_managed_group_protection_constraints(
    node_service: NodeService,
) -> None:
    """Verify that users cannot modify, move, or delete system groups."""
    ws = node_service.create_node(name="WS", node_kind="workspace", auto_layout=True)
    sys_group = next(c for c in node_service.load_children(ws.id) if c.name == "System")

    # Rejects update/modification
    with pytest.raises(
        ValidationError, match="Managed system groups cannot be modified"
    ):
        node_service.update_node(sys_group.id, name="Custom Renamed")

    # Rejects deletion
    with pytest.raises(
        ValidationError, match="Managed system groups cannot be deleted"
    ):
        node_service.delete_node(sys_group.id)

    # Rejects movement
    with pytest.raises(ValidationError, match="Managed system groups cannot be moved"):
        node_service.move_node(sys_group.id, ws.id)
