import uuid

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


def assert_node_belongs_to_workspace(
    node_service: NodeService, node_id: uuid.UUID, workspace_id: uuid.UUID
) -> None:
    """Diagnostic assertion helper ensuring node belongs to expected workspace."""
    ws = node_service._find_workspace_for_node(node_id)
    assert ws is not None, f"Node {node_id} has no workspace ancestor"
    assert ws.id == workspace_id, (
        f"Node {node_id} belongs to workspace {ws.id}, "
        f"expected workspace {workspace_id}"
    )


def test_service_managed_group_lookups_scoped_by_workspace(
    node_service: NodeService,
) -> None:
    """Verify that managed group queries are strictly scoped by workspace_id."""
    ws1 = node_service.create_node(name="WS1", node_kind="workspace", auto_layout=True)
    ws2 = node_service.create_node(name="WS2", node_kind="workspace", auto_layout=True)

    # Scoped custom group lookups
    cg1 = node_service.get_custom_group(ws1.id)
    cg2 = node_service.get_custom_group(ws2.id)
    assert cg1.id != cg2.id
    assert cg1.parent_id == ws1.id
    assert cg2.parent_id == ws2.id

    # Scoped system group lookups
    sg1 = node_service.get_system_group(ws1.id)
    sg2 = node_service.get_system_group(ws2.id)
    assert sg1.id != sg2.id
    assert sg1.parent_id == ws1.id
    assert sg2.parent_id == ws2.id

    # Scoped System subsection lookups
    sub1 = node_service.get_system_subsection(ws1.id, "script")
    sub2 = node_service.get_system_subsection(ws2.id, "script")
    assert sub1.id != sub2.id
    assert sub1.parent_id == sg1.id
    assert sub2.parent_id == sg2.id


def test_resolve_workspace_context_all_kinds(
    node_service: NodeService, ref_service: ResourceReferenceService
) -> None:
    """Verify resolve_workspace_context correctly resolves for all kinds."""
    # 1. Workspace
    ws = node_service.create_node(
        name="Blender WS", node_kind="workspace", auto_layout=True
    )
    assert node_service.resolve_workspace_context(ws.id) == ws.id

    # 2. System and Custom
    sys_group = node_service.get_system_group(ws.id)
    cust_group = node_service.get_custom_group(ws.id)
    assert node_service.resolve_workspace_context(sys_group.id) == ws.id
    assert node_service.resolve_workspace_context(cust_group.id) == ws.id

    # 3. Managed System subsection
    sub = node_service.get_system_subsection(ws.id, "directory")
    assert node_service.resolve_workspace_context(sub.id) == ws.id

    # 4. Nested Custom Folder
    folder = node_service.create_node(
        name="nested", node_kind="folder", parent_id=cust_group.id
    )
    assert node_service.resolve_workspace_context(folder.id) == ws.id

    # 5. Directory
    dir_node = node_service.create_node(
        name="Dir",
        node_kind="resource",
        resource_type="directory",
        parent_id=ws.id,
        auto_route=True,
    )
    assert node_service.resolve_workspace_context(dir_node.id) == ws.id

    # 6. File
    from pathlib import Path

    p = Path("/tmp/f.txt")
    p.touch()
    file_node = node_service.create_node(
        name="File",
        node_kind="resource",
        resource_type="file",
        path="/tmp/f.txt",
        parent_id=ws.id,
        auto_route=True,
    )
    assert node_service.resolve_workspace_context(file_node.id) == ws.id

    # 7. Reference
    ref = ref_service.create_reference(file_node.id, cust_group.id)
    assert node_service.resolve_workspace_context(ref.reference_node_id) == ws.id


def test_resource_reference_persistence_regression_and_all_types(tmp_path):
    import sys

    from pathtree.database.connection import create_db_engine, init_db
    from pathtree.database.repository import (
        LaunchProfileRepository,
        MultiLauncherRepository,
        NodeRepository,
        ResourceReferenceRepository,
    )
    from pathtree.services.launch_profile_service import LaunchProfileService
    from pathtree.services.multi_launcher_service import MultiLauncherService
    from pathtree.services.node_service import NodeService
    from pathtree.services.resource_reference_service import ResourceReferenceService

    db_file = tmp_path / "pathtree_test.db"

    # 1. First session
    engine1 = create_db_engine(db_file)
    init_db(engine1)

    with Session(engine1) as session1:
        ns1 = NodeService(NodeRepository(session1))
        lps1 = LaunchProfileService(ns1, LaunchProfileRepository(session1))
        mls1 = MultiLauncherService(ns1, lps1, MultiLauncherRepository(session1))
        rrs1 = ResourceReferenceService(ns1, ResourceReferenceRepository(session1))

        # 1. create Workspace A
        ws_a = ns1.create_node(
            name="Workspace A", node_kind="workspace", auto_layout=True
        )

        # We need a target script for launch profile
        script_target = ns1.create_node(
            name="Target Script",
            node_kind="resource",
            resource_type="script",
            parent_id=ws_a.id,
            path=__file__,
        )

        # Let's create all 7 types of original resources to be referenced
        # 1. Directory
        dir_res = ns1.create_node(
            name="Dir Res",
            node_kind="resource",
            resource_type="directory",
            parent_id=ws_a.id,
            path=str(tmp_path),
        )
        # 2. File
        file_res = ns1.create_node(
            name="File Res",
            node_kind="resource",
            resource_type="file",
            parent_id=ws_a.id,
            path=__file__,
        )
        # 3. Script
        script_res = ns1.create_node(
            name="Script Res",
            node_kind="resource",
            resource_type="script",
            parent_id=ws_a.id,
            path=__file__,
        )
        # 4. Executable
        exec_res = ns1.create_node(
            name="Exec Res",
            node_kind="resource",
            resource_type="executable",
            parent_id=ws_a.id,
            path=sys.executable,
        )
        # 5. URL
        url_res = ns1.create_node(
            name="URL Res",
            node_kind="resource",
            resource_type="url",
            parent_id=ws_a.id,
            path="https://github.com",
        )
        # 6. Launch Profile
        profile_res = lps1.create_profile(
            name="Profile Res",
            target_node_id=script_target.id,
            arguments=[],
        )
        profile_node = ns1.get_node(profile_res.profile_node_id)

        # 7. Multi Launcher
        ml_res = mls1.create_launcher(
            name="ML Res",
            workspace_id=ws_a.id,
        )
        ml_node = ns1.get_node(ml_res.launcher_node_id)

        # 3. create Workspace B
        ws_b = ns1.create_node(
            name="Workspace B", node_kind="workspace", auto_layout=True
        )

        # 4. create nested folder: Workspace B / Custom / Blender
        custom_b = ns1.get_custom_group(ws_b.id)
        blender_folder = ns1.create_node(
            name="Blender",
            node_kind="folder",
            parent_id=custom_b.id,
        )

        custom_b_id = custom_b.id
        blender_folder_id = blender_folder.id

        # 5. create references inside blender_folder
        ref_ids = {}
        for r_type, orig_node in [
            ("directory", dir_res),
            ("file", file_res),
            ("script", script_res),
            ("executable", exec_res),
            ("url", url_res),
            ("launch_profile", profile_node),
            ("multi_launcher", ml_node),
        ]:
            ref = rrs1.create_reference(
                original_node_id=orig_node.id,
                destination_parent_id=blender_folder_id,
                custom_name=f"Ref {r_type}",
            )
            ref_ids[r_type] = ref.reference_node_id

        session1.commit()

    # 7. create a completely new engine/session/service/application instance
    # 8. reload PathTree
    engine2 = create_db_engine(db_file)
    init_db(engine2)

    with Session(engine2) as session2:
        ns2 = NodeService(NodeRepository(session2))

        # Let's assert:
        # 9. reference.parent_id == Blender folder ID
        # 10. assert the reference appears only under: Workspace B / Custom / Blender
        # 11. assert it does not appear under any System subsection
        for r_type, ref_node_id in ref_ids.items():
            ref_node = ns2.get_node(ref_node_id)
            assert ref_node is not None, (
                f"Reference for {r_type} not found after reload"
            )
            assert ref_node.parent_id == blender_folder_id, (
                f"Reference for {r_type} parent_id mismatch"
            )
            assert ref_node.node_kind == "resource"
            assert ref_node.resource_type == "reference"

            # Check hierarchy: grandparent must be custom_b_id,
            # and it must not be in any system area
            parent = ns2.get_node(ref_node.parent_id)
            assert parent.node_kind == "folder"
            assert parent.parent_id == custom_b_id

            # verify that it is not inside any system area of either workspace
            assert not ns2._is_inside_system_area(ref_node.id)


def test_startup_repair_idempotence(tmp_path):
    from sqlmodel import select

    from pathtree.database.connection import (
        create_db_engine,
        init_db,
        migrate_existing_workspaces,
    )
    from pathtree.database.repository import NodeRepository, ResourceReferenceRepository
    from pathtree.models.node import Node
    from pathtree.models.resource_reference import ResourceReference
    from pathtree.services.node_service import NodeService
    from pathtree.services.resource_reference_service import ResourceReferenceService

    db_file = tmp_path / "idempotence_test.db"

    # Initialize DB
    engine = create_db_engine(db_file)
    init_db(engine)

    with Session(engine) as session:
        ns = NodeService(NodeRepository(session))
        rrs = ResourceReferenceService(ns, ResourceReferenceRepository(session))

        # 1. Create a workspace with auto layout
        ws = ns.create_node(name="Workspace", node_kind="workspace", auto_layout=True)
        custom_group = ns.get_custom_group(ws.id)

        # Create folder in Custom
        folder = ns.create_node(
            name="My Folder", node_kind="folder", parent_id=custom_group.id
        )
        folder_id = folder.id

        # Create a real resource URL
        orig_url = ns.create_node(
            name="URL Target",
            node_kind="resource",
            resource_type="url",
            parent_id=ws.id,
            path="https://target.com",
            auto_route=True,
        )

        # Create reference to the URL inside our custom folder
        ref = rrs.create_reference(
            original_node_id=orig_url.id, destination_parent_id=folder_id
        )
        ref_node_id = ref.reference_node_id
        ref_record_id = ref.id
        orig_node_id = ref.original_node_id

        session.commit()

    # Now let's run layout repair/migration twice.
    # The first run should make no changes to our reference
    # because it is already validly parented.
    with Session(engine) as session1:
        migrate_existing_workspaces(session1.connection())
        session1.commit()

    # Record nodes and references after first run
    with Session(engine) as session_check1:
        nodes_after_first = {
            n.id: n.model_copy() for n in session_check1.exec(select(Node)).all()
        }
        refs_after_first = {
            r.id: r.model_copy()
            for r in session_check1.exec(select(ResourceReference)).all()
        }

    # Second run of layout repair/migration
    with Session(engine) as session2:
        migrate_existing_workspaces(session2.connection())
        session2.commit()

    # Record and assert nodes/references after second run
    with Session(engine) as session_check2:
        nodes_after_second = {
            n.id: n.model_copy() for n in session_check2.exec(select(Node)).all()
        }
        refs_after_second = {
            r.id: r.model_copy()
            for r in session_check2.exec(select(ResourceReference)).all()
        }

    # Assertions:
    # 1. Number of nodes and references is unchanged
    assert len(nodes_after_second) == len(nodes_after_first)
    assert len(refs_after_second) == len(refs_after_first)

    # 2. No reference changes parent, node properties are preserved
    for nid, node1 in nodes_after_first.items():
        node2 = nodes_after_second[nid]
        assert node1.parent_id == node2.parent_id
        assert node1.node_kind == node2.node_kind
        assert node1.resource_type == node2.resource_type
        assert node1.name == node2.name

    # 3. No reference record is duplicated or modified
    for rid, ref1 in refs_after_first.items():
        ref2 = refs_after_second[rid]
        assert ref1.reference_node_id == ref2.reference_node_id
        assert ref1.original_node_id == ref2.original_node_id

    # 4. Confirm our reference node ID and original_node_id remain unchanged
    our_ref_node = nodes_after_second[ref_node_id]
    assert our_ref_node.parent_id == folder_id
    assert our_ref_node.node_kind == "resource"
    assert our_ref_node.resource_type == "reference"

    our_ref_rec = refs_after_second[ref_record_id]
    assert our_ref_rec.reference_node_id == ref_node_id
    assert our_ref_rec.original_node_id == orig_node_id
