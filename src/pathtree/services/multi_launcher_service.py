import time
import uuid
from collections.abc import Callable

from pathtree.database.repository import MultiLauncherRepository
from pathtree.models.multi_launcher import MultiLauncher, MultiLauncherItem
from pathtree.services.launch_profile_service import LaunchProfileService
from pathtree.services.node_service import NodeService, ValidationError


class MultiLauncherServiceError(Exception):
    """Base exception for all multi launcher service errors."""


class LauncherNotFoundError(MultiLauncherServiceError):
    """Raised when the requested multi launcher does not exist."""


class LauncherItemNotFoundError(MultiLauncherServiceError):
    """Raised when the requested multi launcher item does not exist."""


class MultiLauncherService:
    """Service layer managing Multi Launchers and their items.

    Sequential Execution Semantics:
    - Multi Launcher runs Launch Profiles sequentially.
    - It does not wait for process completion (GUI applications or terminal modes
      may return immediately as soon as the launch is initiated).
    - If a profile fails during validation or initiation, execution stops.
    - delay_ms is applied after each item launches, before the next enabled item starts.
    - No delay is applied after the final item.
    - Disabled items do not execute and do not introduce delay.
    """

    def __init__(
        self,
        node_service: NodeService,
        launch_profile_service: LaunchProfileService,
        multi_launcher_repository: MultiLauncherRepository,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        """Initialize MultiLauncherService with injectable sleeper."""
        self.node_service = node_service
        self.launch_profile_service = launch_profile_service
        self.repository = multi_launcher_repository
        self.sleeper = sleeper

    def create_launcher(
        self,
        name: str,
        workspace_id: uuid.UUID,
        description: str | None = None,
        node_id: uuid.UUID | None = None,
    ) -> MultiLauncher:
        """Create a new Multi Launcher and its tree Node representation."""
        workspace = self.node_service.get_node(workspace_id)
        if not workspace or workspace.node_kind != "workspace":
            raise ValidationError("A valid workspace is required.")

        node_created = False
        launcher_node_id = None
        try:
            # 1. Lazy create 'Multi Launchers' system group if node_id is None
            if node_id is None:
                if self.node_service._has_custom_group(workspace_id):
                    group = self.node_service.get_system_subsection(
                        workspace_id, "multi_launcher"
                    )
                else:
                    group = self.node_service.get_or_create_system_group(
                        workspace_id, "multi_launchers", "Multi Launchers"
                    )
                # Create node representation
                node = self.node_service.create_node(
                    name=name,
                    node_kind="resource",
                    resource_type="multi_launcher",
                    parent_id=group.id,
                    description=description,
                )
                launcher_node_id = node.id
                node_created = True
            else:
                launcher_node_id = node_id

            # 2. Create MultiLauncher model record
            launcher = MultiLauncher(
                launcher_node_id=launcher_node_id,
                workspace_id=workspace_id,
                name=name,
                description=description,
            )
            return self.repository.create(launcher)
        except Exception as e:
            # Rollback: Clean up created node to prevent orphans
            if node_created and launcher_node_id is not None:
                try:
                    self.node_service.delete_node(launcher_node_id, recursive=True)
                except Exception:
                    pass
            raise ValidationError(f"Failed to create Multi Launcher: {e}") from e

    def get_launcher(self, launcher_id: uuid.UUID) -> MultiLauncher:
        """Retrieve a Multi Launcher by its ID."""
        launcher = self.repository.get_by_id(launcher_id)
        if not launcher:
            raise LauncherNotFoundError(f"Multi Launcher '{launcher_id}' not found.")
        return launcher

    def get_launcher_for_node(self, launcher_node_id: uuid.UUID) -> MultiLauncher:
        """Retrieve a Multi Launcher by its Node ID."""
        launcher = self.repository.get_by_launcher_node_id(launcher_node_id)
        if not launcher:
            raise LauncherNotFoundError(
                f"Multi Launcher for node '{launcher_node_id}' not found."
            )
        return launcher

    def list_launchers_for_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[MultiLauncher]:
        """List all Multi Launchers belonging to a workspace."""
        return list(self.repository.list_by_workspace(workspace_id))

    def update_launcher(
        self,
        launcher_id: uuid.UUID,
        name: str | None = None,
        description: str | None = None,
    ) -> MultiLauncher:
        """Update Multi Launcher properties."""
        launcher = self.get_launcher(launcher_id)

        # Update node name / description in tree
        if name is not None:
            self.node_service.update_node(
                launcher.launcher_node_id, name=name, description=description
            )
            launcher.name = name

        if description is not None:
            if name is None:
                self.node_service.update_node(
                    launcher.launcher_node_id, description=description
                )
            launcher.description = description

        # Move tree node under workspace's "Multi Launchers" system group upon edit
        try:
            if self.node_service._has_custom_group(launcher.workspace_id):
                group = self.node_service.get_system_subsection(
                    launcher.workspace_id, "multi_launcher"
                )
            else:
                group = self.node_service.get_or_create_system_group(
                    launcher.workspace_id, "multi_launchers", "Multi Launchers"
                )
            node = self.node_service.get_node(launcher.launcher_node_id)
            if node and node.parent_id != group.id:
                self.node_service.move_node(launcher.launcher_node_id, group.id)
        except Exception:
            pass

        return self.repository.update(launcher)

    def delete_launcher(self, launcher_id: uuid.UUID) -> bool:
        """Delete a Multi Launcher and its node representation in the tree."""
        launcher = self.get_launcher(launcher_id)

        # Delete corresponding tree Node (will trigger cascade or manual cleanup)
        try:
            self.node_service.delete_node(launcher.launcher_node_id, recursive=True)
        except Exception:
            pass

        return self.repository.delete(launcher_id)

    def duplicate_launcher(self, launcher_id: uuid.UUID) -> MultiLauncher:
        """Duplicate a Multi Launcher and all its items."""
        orig = self.get_launcher(launcher_id)
        orig_node = self.node_service.get_node(orig.launcher_node_id)
        if not orig_node:
            raise ValidationError("Original launcher node not found.")

        # Resolve duplicate name safely
        copied_name = f"{orig.name} Copy"
        base_name = copied_name
        counter = 1
        while self.node_service.repository.has_sibling_with_name(
            orig_node.parent_id, copied_name
        ):
            copied_name = f"{base_name} ({counter})"
            counter += 1

        new_node_id = None
        new_launcher_id = None
        try:
            # Create new tree node
            new_node = self.node_service.create_node(
                name=copied_name,
                node_kind="resource",
                resource_type="multi_launcher",
                parent_id=orig_node.parent_id,
                description=orig.description,
                icon=orig_node.icon,
            )
            new_node_id = new_node.id

            # Create MultiLauncher
            new_launcher = self.create_launcher(
                name=copied_name,
                workspace_id=orig.workspace_id,
                description=orig.description,
                node_id=new_node.id,
            )
            new_launcher_id = new_launcher.id

            # Duplicate items
            orig_items = self.repository.list_items_for_launcher(launcher_id)
            for item in orig_items:
                new_item = MultiLauncherItem(
                    multi_launcher_id=new_launcher.id,
                    launch_profile_id=item.launch_profile_id,
                    position=item.position,
                    enabled=item.enabled,
                    delay_ms=item.delay_ms,
                )
                self.repository.create_item(new_item)

            return new_launcher
        except Exception as e:
            # Atomic rollback: delete created nodes or records
            if new_launcher_id is not None:
                try:
                    self.repository.delete(new_launcher_id)
                except Exception:
                    pass
            if new_node_id is not None:
                try:
                    self.node_service.delete_node(new_node_id, recursive=True)
                except Exception:
                    pass
            raise ValidationError(f"Failed to duplicate Multi Launcher: {e}") from e

    def _recompact_items(self, launcher_id: uuid.UUID) -> None:
        """Recompact items positions sequentially (1..N)."""
        items = self.repository.list_items_for_launcher(launcher_id)
        for idx, item in enumerate(items):
            expected = idx + 1
            if item.position != expected:
                item.position = expected
                self.repository.update_item(item)

    def add_item(
        self,
        launcher_id: uuid.UUID,
        launch_profile_id: uuid.UUID,
        delay_ms: int = 0,
    ) -> MultiLauncherItem:
        """Add a launch profile to a Multi Launcher."""
        launcher = self.get_launcher(launcher_id)
        # Verify launch profile exists
        profile = self.launch_profile_service.get_profile(launch_profile_id)

        # Workspace ownership check: only allow same-workspace profiles
        if profile.workspace_id != launcher.workspace_id:
            raise ValidationError("Launch Profile must belong to the same Workspace.")

        # Find next position
        existing = self.repository.list_items_for_launcher(launcher_id)
        pos = len(existing) + 1

        item = MultiLauncherItem(
            multi_launcher_id=launcher.id,
            launch_profile_id=launch_profile_id,
            position=pos,
            enabled=True,
            delay_ms=delay_ms,
        )
        return self.repository.create_item(item)

    def remove_item(self, item_id: uuid.UUID) -> bool:
        """Remove an item and recompact remaining positions."""
        item = self.repository.get_item_by_id(item_id)
        if not item:
            raise LauncherItemNotFoundError(f"Item '{item_id}' not found.")

        launcher_id = item.multi_launcher_id
        res = self.repository.delete_item(item_id)
        if res:
            self._recompact_items(launcher_id)
        return res

    def reorder_item(self, item_id: uuid.UUID, direction: str) -> None:
        """Move an item Up or Down within a launcher."""
        item = self.repository.get_item_by_id(item_id)
        if not item:
            raise LauncherItemNotFoundError(f"Item '{item_id}' not found.")

        launcher_id = item.multi_launcher_id
        self._recompact_items(launcher_id)

        # Re-fetch after recompaction
        item = self.repository.get_item_by_id(item_id)
        items = self.repository.list_items_for_launcher(launcher_id)

        curr_pos = item.position
        target_pos = curr_pos - 1 if direction == "up" else curr_pos + 1

        if target_pos < 1 or target_pos > len(items):
            return  # Out of bounds

        # Find item at target position
        other = next((it for it in items if it.position == target_pos), None)
        if other:
            # Swap positions
            item.position = target_pos
            other.position = curr_pos
            self.repository.update_item(item)
            self.repository.update_item(other)

    def set_item_enabled(self, item_id: uuid.UUID, enabled: bool) -> None:
        """Enable or disable a launcher item."""
        item = self.repository.get_item_by_id(item_id)
        if not item:
            raise LauncherItemNotFoundError(f"Item '{item_id}' not found.")
        item.enabled = enabled
        self.repository.update_item(item)

    def set_item_delay(self, item_id: uuid.UUID, delay_ms: int) -> None:
        """Update delay in milliseconds for an item."""
        if delay_ms < 0:
            raise ValidationError("Delay must be a non-negative integer.")
        item = self.repository.get_item_by_id(item_id)
        if not item:
            raise LauncherItemNotFoundError(f"Item '{item_id}' not found.")
        item.delay_ms = delay_ms
        self.repository.update_item(item)

    def execute_launcher(self, launcher_id: uuid.UUID) -> None:
        """Execute all enabled launch profiles sequentially.

        Delay is applied after that item launches, before the next enabled item starts.
        The final enabled item does not introduce delay.
        """
        launcher = self.get_launcher(launcher_id)
        items = self.repository.list_items_for_launcher(launcher.id)

        # Filter out disabled items
        enabled_items = [item for item in items if item.enabled]

        for idx, item in enumerate(enabled_items):
            # 1. Fetch profile and report clear errors on stale/detached states
            try:
                profile = self.launch_profile_service.get_profile(
                    item.launch_profile_id
                )
            except Exception as e:
                raise ValidationError(
                    f"Launch Profile for item {item.position} not found: {e}"
                ) from e

            p_node = self.node_service.get_node(profile.profile_node_id)
            p_name = p_node.name if p_node else f"Profile {item.launch_profile_id}"

            if profile.status != "active":
                raise ValidationError(
                    f"Launch Profile '{p_name}' is detached and cannot be executed."
                )

            # 2. Execute launch profile (stops sequentially if it fails)
            self.launch_profile_service.execute_profile(profile.id)

            # 3. Apply delay strictly after launch, only if not the final item
            if idx < len(enabled_items) - 1 and item.delay_ms > 0:
                self.sleeper(item.delay_ms / 1000.0)
