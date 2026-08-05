import json
import uuid
from pathlib import Path

from pathtree.database.repository import LaunchProfileRepository
from pathtree.models.launch_profile import LaunchProfile
from pathtree.models.node import Node
from pathtree.services.node_service import (
    NodeService,
    NodeServiceError,
    ValidationError,
)
from pathtree.utils.launcher import PlatformLauncher, ProcessLaunchResult
from pathtree.utils.script_resolver import resolve_script_argv


class LaunchProfileServiceError(Exception):
    """Base exception for all launch profile service errors."""


class ProfileNotFoundError(LaunchProfileServiceError):
    """Raised when the requested launch profile does not exist."""


class TargetNotFoundError(LaunchProfileServiceError):
    """Raised when the target Script or Executable node does not exist."""


class DetachedProfileError(LaunchProfileServiceError):
    """Raised when trying to execute or run a detached launch profile."""


class InvalidTargetTypeError(LaunchProfileServiceError):
    """Raised when the target node is of an incompatible resource type."""


class InvalidWorkingDirectoryError(LaunchProfileServiceError):
    """Raised when the working directory node is not a valid Directory resource."""


class InvalidArgumentDataError(LaunchProfileServiceError):
    """Raised when arguments format is invalid."""


class DuplicateManagedGroupError(LaunchProfileServiceError):
    """Raised when a duplicate managed system group creation is detected/prevented."""


class ExecutionFailureError(LaunchProfileServiceError):
    """Raised when process/script execution fails."""


class LaunchProfileService:
    """Service layer managing Launch Profiles creation, update, and execution."""

    def __init__(
        self,
        node_service: NodeService,
        launch_profile_repository: LaunchProfileRepository,
    ) -> None:
        """Initialize the LaunchProfileService."""
        self.node_service = node_service
        self.launch_profile_repository = launch_profile_repository

    def find_originating_workspace(self, node_id: uuid.UUID) -> Node | None:
        """Find the Workspace ancestor of a node."""
        curr = self.node_service.get_node(node_id)
        while curr is not None:
            if curr.node_kind == "workspace":
                return curr
            if curr.parent_id is None:
                break
            curr = self.node_service.get_node(curr.parent_id)
        return None

    def create_profile(
        self,
        name: str,
        target_node_id: uuid.UUID,
        arguments: list[str],
        working_directory_node_id: uuid.UUID | None = None,
        terminal_mode: str = "inherit",
    ) -> LaunchProfile:
        """Create a new Launch Profile from a target Script or Executable."""
        # 1. Resolve target node
        target_node = self.node_service.get_node(target_node_id)
        if not target_node:
            raise TargetNotFoundError(f"Target node '{target_node_id}' not found.")

        # Compatibility check
        if target_node.node_kind != "resource" or target_node.resource_type not in (
            "script",
            "executable",
        ):
            raise InvalidTargetTypeError(
                f"Incompatible target resource type: {target_node.resource_type}. "
                "Must be either 'script' or 'executable'."
            )

        # 2. Determine originating workspace
        workspace = self.find_originating_workspace(target_node_id)
        if not workspace:
            raise TargetNotFoundError("Target node is not within any workspace.")

        # 3. Find or create the "Launch Profiles" system group section lazily
        try:
            launch_profiles_group = self.node_service.get_or_create_system_group(
                workspace.id, "launch_profiles", "Launch Profiles"
            )
        except ValidationError as e:
            raise DuplicateManagedGroupError(str(e)) from e

        # 4. Create Directory/Resource node for the profile
        try:
            profile_node = self.node_service.create_node(
                name=name,
                node_kind="resource",
                resource_type="launch_profile",
                parent_id=launch_profiles_group.id,
            )
        except NodeServiceError as e:
            raise LaunchProfileServiceError(str(e)) from e

        # 5. Validate working directory if provided
        if working_directory_node_id is not None:
            wd_node = self.node_service.get_node(working_directory_node_id)
            if (
                not wd_node
                or wd_node.node_kind != "resource"
                or wd_node.resource_type != "directory"
            ):
                raise InvalidWorkingDirectoryError(
                    "Working directory must refer to an existing Directory resource node."
                )

        # 6. Create LaunchProfile model record
        profile = LaunchProfile(
            profile_node_id=profile_node.id,
            workspace_id=workspace.id,
            target_node_id=target_node.id,
            target_resource_type=target_node.resource_type,
            arguments=json.dumps(arguments),
            working_directory_node_id=working_directory_node_id,
            terminal_mode=terminal_mode,
            status="active",
        )

        return self.launch_profile_repository.create(profile)

    def get_profile(self, profile_id: uuid.UUID) -> LaunchProfile:
        """Retrieve a LaunchProfile by its ID."""
        profile = self.launch_profile_repository.get_by_id(profile_id)
        if not profile:
            raise ProfileNotFoundError(f"Launch Profile '{profile_id}' not found.")
        return profile

    def get_profile_for_node(self, profile_node_id: uuid.UUID) -> LaunchProfile:
        """Retrieve a LaunchProfile associated with a tree Node ID."""
        profile = self.launch_profile_repository.get_by_profile_node_id(profile_node_id)
        if not profile:
            raise ProfileNotFoundError(
                f"Launch Profile for node '{profile_node_id}' not found."
            )
        return profile

    def list_profiles_for_workspace(
        self, workspace_id: uuid.UUID
    ) -> list[LaunchProfile]:
        """List all Launch Profiles for a given Workspace."""
        return list(self.launch_profile_repository.list_by_workspace(workspace_id))

    def list_profiles_for_target(
        self, target_node_id: uuid.UUID
    ) -> list[LaunchProfile]:
        """List all Launch Profiles connected to a target node."""
        return list(self.launch_profile_repository.list_by_target(target_node_id))

    def update_profile(
        self,
        profile_id: uuid.UUID,
        name: str | None = None,
        target_node_id: uuid.UUID | None = None,
        arguments: list[str] | None = None,
        working_directory_node_id: uuid.UUID | None = None,
        clear_working_directory: bool = False,
        terminal_mode: str | None = None,
        status: str | None = None,
    ) -> LaunchProfile:
        """Update properties of an existing Launch Profile."""
        profile = self.get_profile(profile_id)

        # 1. Update Profile name in tree
        if name is not None:
            profile_node = self.node_service.get_node(profile.profile_node_id)
            if profile_node:
                self.node_service.update_node(profile_node.id, name=name)

        # 2. Reconnect/update target node
        if target_node_id is not None:
            target_node = self.node_service.get_node(target_node_id)
            if not target_node:
                raise TargetNotFoundError(f"Target node '{target_node_id}' not found.")

            if (
                target_node.node_kind != "resource"
                or target_node.resource_type != profile.target_resource_type
            ):
                raise InvalidTargetTypeError(
                    f"Incompatible target type: '{target_node.resource_type}'. "
                    f"Profile target type is originally restricted to '{profile.target_resource_type}'."
                )

            profile.target_node_id = target_node_id
            profile.status = "active"
            profile.previous_target_name = None
            profile.previous_target_path = None

            # Automatically move profile tree node back under Launch Profiles
            try:
                launch_group = self.node_service.get_or_create_system_group(
                    profile.workspace_id, "launch_profiles", "Launch Profiles"
                )
                self.node_service.move_node(profile.profile_node_id, launch_group.id)
            except Exception:
                pass

        if arguments is not None:
            if not isinstance(arguments, list):
                raise InvalidArgumentDataError("Arguments must be a list of strings.")
            profile.arguments = json.dumps(arguments)

        if clear_working_directory:
            profile.working_directory_node_id = None
        elif working_directory_node_id is not None:
            wd_node = self.node_service.get_node(working_directory_node_id)
            if (
                not wd_node
                or wd_node.node_kind != "resource"
                or wd_node.resource_type != "directory"
            ):
                raise InvalidWorkingDirectoryError(
                    "Working directory must refer to an existing Directory resource node."
                )
            profile.working_directory_node_id = working_directory_node_id

        if terminal_mode is not None:
            profile.terminal_mode = terminal_mode

        if status is not None:
            profile.status = status

        return self.launch_profile_repository.update(profile)

    def reconnect_profile(
        self, profile_id: uuid.UUID, target_node_id: uuid.UUID
    ) -> LaunchProfile:
        """Reconnect a Launch Profile to a compatible target node."""
        return self.update_profile(profile_id, target_node_id=target_node_id)

    def delete_profile(self, profile_id: uuid.UUID) -> bool:
        """Delete only that profile record and its node representation in the tree."""
        profile = self.get_profile(profile_id)

        # Delete corresponding tree Node
        try:
            self.node_service.delete_node(profile.profile_node_id, recursive=True)
        except Exception:
            pass

        # Delete referencing MultiLauncherItems to avoid foreign key violations
        from sqlmodel import delete

        from pathtree.models.multi_launcher import MultiLauncherItem

        try:
            statement = delete(MultiLauncherItem).where(
                MultiLauncherItem.launch_profile_id == profile_id
            )
            self.launch_profile_repository.session.exec(statement)
            self.launch_profile_repository.session.flush()
        except Exception:
            pass

        # Delete profile record
        return self.launch_profile_repository.delete(profile_id)

    def detach_profiles_for_target(self, target_node_id: uuid.UUID) -> None:
        """Explicitly detach any Launch Profiles targeting a node."""
        target_node = self.node_service.get_node(target_node_id)
        if not target_node:
            raise TargetNotFoundError(f"Target node '{target_node_id}' not found.")

        profiles = self.launch_profile_repository.list_by_target(target_node_id)
        for profile in profiles:
            profile.previous_target_name = target_node.name
            profile.previous_target_path = target_node.path
            profile.target_node_id = None
            profile.status = "detached"

            # Move profile tree node to Detached Profiles
            workspace = self.find_originating_workspace(target_node_id)
            if workspace:
                try:
                    detached_group = self.node_service.get_or_create_system_group(
                        workspace.id,
                        "detached_launch_profiles",
                        "Detached Profiles",
                    )
                    self.node_service.move_node(
                        profile.profile_node_id, detached_group.id
                    )
                except Exception:
                    pass

            self.launch_profile_repository.update(profile)

    def resolve_arguments(self, profile_id: uuid.UUID) -> list[str]:
        """Resolve arguments list for a launch profile."""
        profile = self.get_profile(profile_id)
        return profile.argv

    def resolve_working_directory(self, profile_id: uuid.UUID) -> Path | None:
        """Resolve working directory path if specified."""
        profile = self.get_profile(profile_id)
        if profile.working_directory_node_id is None:
            return None

        try:
            return self.node_service.resolve_node_path(
                profile.working_directory_node_id
            )
        except Exception as e:
            raise InvalidWorkingDirectoryError(
                f"Failed to resolve working directory: {e}"
            ) from e

    def execute_profile(
        self, profile_id: uuid.UUID, terminal_mode_override: str | None = None
    ) -> ProcessLaunchResult:
        """Execute a Launch Profile through Script or Executable infrastructure."""
        # 1. Verify profile exists
        profile = self.get_profile(profile_id)

        # 2. Verify profile is active
        if profile.status != "active" or profile.target_node_id is None:
            raise DetachedProfileError("Cannot execute a detached launch profile.")

        # 3. Resolve target node
        target_node = self.node_service.get_node(profile.target_node_id)
        if not target_node:
            raise TargetNotFoundError(
                f"Target node '{profile.target_node_id}' not found."
            )

        # Verify target node compatibility
        if (
            target_node.node_kind != "resource"
            or target_node.resource_type != profile.target_resource_type
        ):
            raise InvalidTargetTypeError(
                f"Target node resource type '{target_node.resource_type}' is incompatible "
                f"with profile target resource type '{profile.target_resource_type}'."
            )

        # 4. Resolve target node path
        try:
            target_path = self.node_service.resolve_node_path(target_node.id)
        except Exception as e:
            raise ExecutionFailureError(
                f"Failed to resolve target node path: {e}"
            ) from e

        # 5. Build explicit argv safely
        if target_node.resource_type == "script":
            try:
                base_argv = resolve_script_argv(target_path)
            except Exception as e:
                raise ExecutionFailureError(
                    f"Failed to resolve script interpreter: {e}"
                ) from e
        else:
            # executable
            try:
                if not str(target_path):
                    raise ValueError("Executable path cannot be empty.")
                if not target_path.exists():
                    raise FileNotFoundError(
                        f"Executable path '{target_path}' does not exist."
                    )
                if not target_path.is_file():
                    raise IsADirectoryError(
                        f"Executable path '{target_path}' is a directory."
                    )
                self.node_service.validate_executable_path(target_path)
            except Exception as e:
                raise ExecutionFailureError(f"Executable validation failed: {e}") from e
            base_argv = [str(target_path)]

        # Combine base argv with custom profile arguments
        argv = base_argv + profile.argv

        # 6. Resolve optional working directory
        if profile.working_directory_node_id is not None:
            try:
                cwd = self.node_service.resolve_node_path(
                    profile.working_directory_node_id
                )
            except Exception as e:
                raise InvalidWorkingDirectoryError(
                    f"Failed to resolve working directory: {e}"
                ) from e
        else:
            cwd = target_path.parent

        # 7. Execute according to terminal mode
        t_mode = terminal_mode_override or profile.terminal_mode
        if t_mode == "new_terminal":
            res = PlatformLauncher.launch_in_terminal(argv, cwd=cwd)
        else:
            res = PlatformLauncher.launch_process(argv, cwd=cwd)

        if not res.success:
            raise ExecutionFailureError(res.error_message or "Process launch failed.")

        return res
