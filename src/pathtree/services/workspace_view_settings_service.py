import uuid

from pathtree.database.repository import WorkspaceViewSettingsRepository
from pathtree.models.workspace_view_settings import WorkspaceViewSettings
from pathtree.services.node_service import TreeNode

# Bitmask values for resource filters
DIRECTORIES = 1 << 0  # 1
FILES = 1 << 1  # 2
SCRIPTS = 1 << 2  # 4
EXECUTABLES = 1 << 3  # 8
URLS = 1 << 4  # 16
LAUNCH_PROFILES = 1 << 5  # 32
MULTI_LAUNCHERS = 1 << 6  # 64
CUSTOM = 1 << 7  # 128


class WorkspaceViewSettingsService:
    """Service layer coordinating WorkspaceViewSettings business operations."""

    def __init__(self, repository: WorkspaceViewSettingsRepository) -> None:
        """Initialize the WorkspaceViewSettingsService."""
        self.repository = repository
        self._cache: dict[uuid.UUID, WorkspaceViewSettings] = {}

    def get_settings(self, workspace_id: uuid.UUID) -> WorkspaceViewSettings:
        """Retrieve view settings for a Workspace.

        Uses memory cache if available, falling back to database.
        If no database record exists, creates a transient default record in memory.
        It is only persisted to the database on an actual view state change.
        """
        if workspace_id in self._cache:
            return self._cache[workspace_id]

        settings = self.repository.get_by_workspace_id(workspace_id)
        if settings is None:
            # Create transient default settings in memory (not persisted yet)
            settings = WorkspaceViewSettings(
                workspace_id=workspace_id,
                current_mode="all",
                last_filter_mask=0,
                hide_empty_sections=False,
                show_system=True,
                show_custom=True,
            )

        self._cache[workspace_id] = settings
        return settings

    def save_settings(self, settings: WorkspaceViewSettings) -> WorkspaceViewSettings:
        """Save/update settings both in memory and the database.

        If the settings record is transient, inserts it using create.
        Otherwise, updates it using update.
        """
        existing = self.repository.get_by_workspace_id(settings.workspace_id)
        if existing is None:
            updated = self.repository.create(settings)
        else:
            updated = self.repository.update(settings)
        self._cache[settings.workspace_id] = updated
        return updated

    def clear_settings(self, workspace_id: uuid.UUID) -> WorkspaceViewSettings:
        """Delete stored view settings or reset them to defaults.

        After clear, returns to 'all' mode with filters cleared.
        """
        settings = self.get_settings(workspace_id)
        settings.current_mode = "all"
        settings.last_filter_mask = 0
        settings.show_system = True
        settings.show_custom = True
        # Note: hide_empty_sections remains independent
        updated = self.save_settings(settings)
        return updated

    def has_active_filter(self, workspace_id: uuid.UUID) -> bool:
        """Determine if a workspace has any active non-default view settings."""
        settings = self.get_settings(workspace_id)
        if settings.current_mode == "filter":
            return True
        if settings.hide_empty_sections:
            return True
        if not settings.show_system or not settings.show_custom:
            return True
        return False

    def filter_tree(self, tree_nodes: list[TreeNode]) -> list[TreeNode]:
        """Apply active workspace view filters to a list of root TreeNodes in memory.

        Does not modify the original node hierarchy structure or run database queries.
        """
        return [self._filter_node(node) for node in tree_nodes]

    def _filter_node(self, tn: TreeNode) -> TreeNode:
        if tn.node.node_kind == "workspace":
            ws_id = tn.node.id
            settings = self.get_settings(ws_id)

            if settings.current_mode == "all":
                if not settings.hide_empty_sections:
                    return tn
                else:
                    # Filter empty managed subsections
                    filtered_children = []
                    for child in tn.children:
                        is_sys_node = (
                            child.node.node_kind == "system_group"
                            and child.node.system_role == "system"
                        )
                        if is_sys_node:
                            new_subsections = []
                            for sub in child.children:
                                is_managed_sub = (
                                    sub.node.node_kind == "system_group"
                                    and sub.node.system_role
                                    in (
                                        "directories",
                                        "files",
                                        "scripts",
                                        "executables",
                                        "urls",
                                        "launch_profiles",
                                        "multi_launchers",
                                    )
                                )
                                if is_managed_sub:
                                    if sub.children:
                                        new_subsections.append(sub)
                                else:
                                    new_subsections.append(sub)
                            filtered_children.append(
                                TreeNode(child.node, new_subsections)
                            )
                        else:
                            filtered_children.append(child)
                    return TreeNode(tn.node, filtered_children)

            # Filter View active
            # Custom visibility
            show_custom = settings.show_custom or bool(
                settings.last_filter_mask & CUSTOM
            )
            # System visibility
            show_system = settings.show_system or bool(
                settings.last_filter_mask & ~CUSTOM
            )

            filtered_children = []
            for child in tn.children:
                is_sys_node = (
                    child.node.node_kind == "system_group"
                    and child.node.system_role == "system"
                )
                if is_sys_node:
                    if not show_system:
                        continue

                    new_subsections = []
                    for sub in child.children:
                        is_managed_sub = (
                            sub.node.node_kind == "system_group"
                            and sub.node.system_role
                            in (
                                "directories",
                                "files",
                                "scripts",
                                "executables",
                                "urls",
                                "launch_profiles",
                                "multi_launchers",
                            )
                        )
                        if is_managed_sub:
                            role_to_bit = {
                                "directories": DIRECTORIES,
                                "files": FILES,
                                "scripts": SCRIPTS,
                                "executables": EXECUTABLES,
                                "urls": URLS,
                                "launch_profiles": LAUNCH_PROFILES,
                                "multi_launchers": MULTI_LAUNCHERS,
                            }
                            bit = role_to_bit.get(sub.node.system_role)
                            has_resource_filters = bool(
                                settings.last_filter_mask & ~CUSTOM
                            )

                            if has_resource_filters:
                                if bit and (settings.last_filter_mask & bit):
                                    is_empty_filtered = (
                                        settings.hide_empty_sections
                                        and not sub.children
                                    )
                                    if not is_empty_filtered:
                                        new_subsections.append(sub)
                            else:
                                is_empty_filtered = (
                                    settings.hide_empty_sections and not sub.children
                                )
                                if not is_empty_filtered:
                                    new_subsections.append(sub)
                        else:
                            new_subsections.append(sub)
                    filtered_children.append(TreeNode(child.node, new_subsections))

                elif (
                    child.node.node_kind == "system_group"
                    and child.node.system_role == "custom"
                ):
                    if show_custom:
                        filtered_children.append(child)
                else:
                    filtered_children.append(child)

            return TreeNode(tn.node, filtered_children)
        else:
            # For other nodes (like workspace_group), recursively filter children
            new_children = [self._filter_node(child) for child in tn.children]
            return TreeNode(tn.node, new_children)
