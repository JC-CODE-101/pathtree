import argparse
import sys
import uuid

from pathtree.database.connection import get_session
from pathtree.database.repository import NodeRepository
from pathtree.services.node_service import NodeService
from pathtree.services.seed import seed_development_data


def get_originating_workspace(node_service: NodeService, node) -> str:
    """Climb the parent hierarchy to find the Workspace node's name."""
    curr = node
    while curr is not None:
        if curr.node_kind == "workspace":
            return curr.name
        if curr.parent_id is None:
            break
        curr = node_service.get_node(curr.parent_id)
    return "Root"


def main() -> None:
    """CLI entry point for PathTree."""

    if len(sys.argv) > 1 and sys.argv[1] == "config":
        if len(sys.argv) >= 5 and sys.argv[2] == "set" and sys.argv[3] == "icons":
            mode = sys.argv[4].lower()
            if mode not in ("nerd", "unicode", "ascii", "auto"):
                print(
                    "Error: Invalid icon mode. Choose from nerd, unicode, ascii, auto.",
                    file=sys.stderr,
                )
                sys.exit(1)
            from pathtree.config.manager import config_manager

            config_manager.set_icon_mode(mode)
            print(f"Icon mode set to '{mode}'.")
            sys.exit(0)
        else:
            print(
                "Usage: pathtree config set icons [nerd|unicode|ascii|auto]",
                file=sys.stderr,
            )
            sys.exit(1)

    parser = argparse.ArgumentParser(
        description="PathTree: Modern terminal workspace and path manager."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=str,
        help="Path to a temporary file where selected directory path will be written.",
    )
    parser.add_argument(
        "--seed-dev",
        action="store_true",
        help="Idempotently seed development data into the database.",
    )
    parser.add_argument(
        "--pins",
        "-p",
        nargs="?",
        const=True,
        type=str,
        help="List all pins, or activate a pin by its numeric position.",
    )
    parser.add_argument(
        "--pin",
        type=str,
        help="Pin an existing node by its stable UUID.",
    )
    parser.add_argument(
        "--unpin",
        type=str,
        help="Unpin a node by its visible numeric position.",
    )
    parser.add_argument(
        "--directories",
        "-d",
        action="store_true",
        help="Filter pins to show only directory resources.",
    )
    parser.add_argument(
        "--files",
        "-f",
        action="store_true",
        help="Filter pins to show only file resources.",
    )
    parser.add_argument(
        "--scripts",
        "-s",
        action="store_true",
        help="Filter pins to show only script resources.",
    )
    parser.add_argument(
        "--executables",
        "-x",
        action="store_true",
        help="Filter pins to show only executable resources.",
    )
    parser.add_argument(
        "--urls",
        "-u",
        action="store_true",
        help="Filter pins to show only URL resources.",
    )
    parser.add_argument(
        "--value",
        action="store_true",
        help=(
            "Output only the target path or URL of the activated pin to "
            "stdout without running actions."
        ),
    )
    parser.add_argument(
        "--values",
        action="store_true",
        help=(
            "Output raw values of all matched pins (one per line) "
            "instead of formatting a table."
        ),
    )
    parser.add_argument(
        "--profiles",
        action="store_true",
        help="List all active and detached launch profiles.",
    )
    parser.add_argument(
        "--profile",
        type=str,
        help="Run a launch profile by its visible numeric position.",
    )
    parser.add_argument(
        "--multi-launchers",
        action="store_true",
        help="List all multi launchers.",
    )
    parser.add_argument(
        "--multi-launcher",
        type=str,
        help="Run a multi launcher by its visible numeric position.",
    )
    override_group = parser.add_mutually_exclusive_group()
    override_group.add_argument(
        "--here",
        action="store_true",
        help="Override the profile execution to run in the current terminal context.",
    )
    override_group.add_argument(
        "--new-terminal",
        action="store_true",
        help="Override the profile execution to run in a new terminal window.",
    )
    parser.add_argument(
        "--icon-preview",
        action="store_true",
        help="Show a preview of every semantic icon in the active mode.",
    )

    args = parser.parse_args()

    if args.icon_preview:
        from pathtree.utils.icons import icon_registry

        mode = icon_registry.get_icon_mode()
        print(f"Active Icon Mode: {mode}\n")

        preview_items = [
            ("Workspace", "workspace", None, None),
            ("System", "system_group", None, "system"),
            ("Custom", "system_group", None, "custom"),
            ("Directories group", "system_group", None, "directories"),
            ("Files group", "system_group", None, "files"),
            ("Scripts group", "system_group", None, "scripts"),
            ("Executables group", "system_group", None, "executables"),
            ("URLs group", "system_group", None, "urls"),
            ("Launch Profiles group", "system_group", None, "launch_profiles"),
            ("Multi Launchers group", "system_group", None, "multi_launchers"),
            ("Folder", "folder", None, None),
            ("Directory", "resource", "directory", None),
            ("File", "resource", "file", None),
            ("Script", "resource", "script", None),
            ("Executable", "resource", "executable", None),
            ("URL", "resource", "url", None),
            ("Launch Profile", "resource", "launch_profile", None),
            ("Multi Launcher", "resource", "multi_launcher", None),
            ("Reference", "resource", "reference", None),
            ("Broken Reference", "resource", "reference", None, True),
        ]

        for item in preview_items:
            label = item[0]
            kind = item[1]
            res_type = item[2]
            role = item[3]
            is_broken = len(item) > 4 and item[4]

            icon = icon_registry.resolve(
                node_kind=kind,
                resource_type=res_type,
                system_role=role,
                is_reference=(res_type == "reference"),
                is_broken=is_broken,
            )

            if res_type == "reference":
                if is_broken:
                    print(f"{icon} {label}")
                else:
                    orig_icon = icon_registry.resolve("resource", "launch_profile")
                    print(
                        f"{orig_icon} Launch Profile {icon} (Reference to Launch Profile)"
                    )
            else:
                print(f"{icon} {label}")

        sys.exit(0)

    # Reject overrides when --profile is not supplied
    if (args.here or args.new_terminal) and args.profile is None:
        parser.error("argument --here or --new-terminal is only allowed with --profile")

    # CLI Multi Launcher list or execution
    if args.multi_launchers or args.multi_launcher is not None:
        with get_session() as session:
            node_repo = NodeRepository(session)
            node_service = NodeService(node_repo)

            from pathtree.database.repository import (
                LaunchProfileRepository,
                MultiLauncherRepository,
            )
            from pathtree.services.launch_profile_service import LaunchProfileService
            from pathtree.services.multi_launcher_service import (
                MultiLauncherService,
            )

            lp_repo = LaunchProfileRepository(session)
            lp_service = LaunchProfileService(node_service, lp_repo)
            ml_repo = MultiLauncherRepository(session)
            ml_service = MultiLauncherService(node_service, lp_service, ml_repo)

            # Retrieve all multi launcher nodes deterministically sorted
            all_nodes = node_service.repository.list_all()
            ml_nodes = [
                node
                for node in all_nodes
                if node.node_kind == "resource"
                and node.resource_type == "multi_launcher"
            ]

            visible_launchers = []
            for node in ml_nodes:
                try:
                    launcher = ml_service.get_launcher_for_node(node.id)
                    visible_launchers.append((launcher, node))
                except Exception:
                    pass

            # Deterministic sorting: sort by parent_id, sort_order, created_at
            visible_launchers.sort(
                key=lambda x: (
                    x[1].parent_id or uuid.UUID(int=0),
                    x[1].sort_order,
                    x[1].created_at,
                )
            )

            # 1. List multi launchers
            if args.multi_launchers:
                for idx, (launcher, node) in enumerate(visible_launchers):
                    visible_pos = idx + 1
                    name = node.name
                    workspace = get_originating_workspace(node_service, node)
                    desc = launcher.description or ""

                    print(f"{visible_pos:<5}{name:<25}{workspace:<15}{desc}")
                sys.exit(0)

            # 2. Run multi launcher
            if args.multi_launcher is not None:
                try:
                    pos = int(args.multi_launcher)
                    if pos < 1:
                        raise ValueError
                except ValueError:
                    print(
                        "Error: Invalid multi launcher position. "
                        "Must be a positive integer.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                if pos > len(visible_launchers):
                    print(
                        f"Error: Invalid multi launcher position {pos}. "
                        "No multi launcher found at that position.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                launcher, node = visible_launchers[pos - 1]

                # Execute multi launcher
                try:
                    ml_service.execute_launcher(launcher.id)
                    print(f"Launched multi launcher: {node.name}")
                    sys.exit(0)
                except Exception as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

    # CLI Launch Profile list or execution
    if args.profiles or args.profile is not None:
        with get_session() as session:
            node_repo = NodeRepository(session)
            node_service = NodeService(node_repo)

            from pathtree.database.repository import LaunchProfileRepository
            from pathtree.services.launch_profile_service import (
                LaunchProfileService,
                LaunchProfileServiceError,
            )

            lp_repo = LaunchProfileRepository(session)
            lp_service = LaunchProfileService(node_service, lp_repo)

            # Retrieve all launch profile nodes deterministically sorted
            all_nodes = node_service.repository.list_all()
            profile_nodes = [
                node
                for node in all_nodes
                if node.node_kind == "resource"
                and node.resource_type == "launch_profile"
            ]

            visible_profiles = []
            for node in profile_nodes:
                try:
                    profile = lp_service.get_profile_for_node(node.id)
                    visible_profiles.append((profile, node))
                except Exception:
                    pass

            # 1. List launch profiles
            if args.profiles:
                for idx, (profile, node) in enumerate(visible_profiles):
                    visible_pos = idx + 1
                    name = node.name
                    workspace = get_originating_workspace(node_service, node)

                    status = profile.status
                    res_type = profile.target_resource_type

                    if profile.target_node_id:
                        t_node = node_service.get_node(profile.target_node_id)
                        target_name = t_node.name if t_node else "Unknown"
                    else:
                        target_name = profile.previous_target_name or "None"

                    print(
                        f"{visible_pos:<5}{name:<25}{workspace:<15}"
                        f"{target_name:<20}{res_type:<12}{status}"
                    )
                sys.exit(0)

            # 2. Run launch profile
            if args.profile is not None:
                try:
                    pos = int(args.profile)
                    if pos < 1:
                        raise ValueError
                except ValueError:
                    print(
                        "Error: Invalid profile position. Must be a positive integer.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                if pos > len(visible_profiles):
                    print(
                        f"Error: Invalid profile position {pos}. "
                        "No profile found at that position.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                profile, node = visible_profiles[pos - 1]

                # Verify active status
                if profile.status != "active":
                    print(
                        f'Error: Launch Profile "{node.name}" is detached.\n'
                        "Reconnect a compatible executable before running it.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                # Determine terminal mode override
                terminal_mode_override = None
                if args.here:
                    terminal_mode_override = "inherit"
                elif args.new_terminal:
                    terminal_mode_override = "new_terminal"

                # Execute profile
                try:
                    lp_service.execute_profile(
                        profile.id, terminal_mode_override=terminal_mode_override
                    )
                    print(f"Launched profile: {node.name}")
                    sys.exit(0)
                except LaunchProfileServiceError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

    if args.seed_dev:
        with get_session() as session:
            repository = NodeRepository(session)
            seed_development_data(repository)
        print("Development seed data populated successfully.")
        sys.exit(0)

    # CLI Management or Pin List operations
    if (
        args.pin is not None
        or args.unpin is not None
        or args.pins is not None
        or args.directories
        or args.files
        or args.scripts
        or args.executables
        or args.urls
    ):
        with get_session() as session:
            node_repo = NodeRepository(session)
            node_service = NodeService(node_repo)

            from pathtree.database.repository import PinRepository
            from pathtree.services.pin_service import PinService, PinServiceError

            pin_repo = PinRepository(session)
            pin_service = PinService(node_repo, pin_repo)

            # 1. Pin management (add pin)
            if args.pin is not None:
                try:
                    node_id = uuid.UUID(args.pin)
                except ValueError:
                    print("Error: Invalid UUID format.", file=sys.stderr)
                    sys.exit(1)

                node = node_service.get_node(node_id)
                if node is None:
                    print(f"Error: Node {node_id} does not exist.", file=sys.stderr)
                    sys.exit(1)

                try:
                    pin_service.pin_node(node_id)
                    print(f'Pinned "{node.name}" successfully.')
                    sys.exit(0)
                except PinServiceError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

            # Build visible CLI pins list (filtering out structural kinds)
            all_pins = pin_service.list_pins()
            visible_pins = []
            for pin in all_pins:
                node = node_service.get_node(pin.node_id)
                if node is not None and node.node_kind == "resource":
                    visible_pins.append((pin, node))

            # Apply explicit type filters
            has_filter = (
                args.directories
                or args.files
                or args.scripts
                or args.executables
                or args.urls
            )
            if has_filter:
                filtered_pins = []
                for pin, node in visible_pins:
                    res_type = node.resource_type
                    if args.directories and res_type == "directory":
                        filtered_pins.append((pin, node))
                    elif args.files and res_type == "file":
                        filtered_pins.append((pin, node))
                    elif args.scripts and res_type == "script":
                        filtered_pins.append((pin, node))
                    elif args.executables and res_type == "executable":
                        filtered_pins.append((pin, node))
                    elif args.urls and res_type == "url":
                        filtered_pins.append((pin, node))
                visible_pins = filtered_pins

            # 2. Unpin management (uses visible position)
            if args.unpin is not None:
                try:
                    pos = int(args.unpin)
                    if pos < 1:
                        raise ValueError
                except ValueError:
                    print(
                        "Error: Invalid pin position. Must be a positive integer.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                if pos > len(visible_pins):
                    print(
                        f"Error: Invalid pin position {pos}. "
                        "No pin found at that position.",
                        file=sys.stderr,
                    )
                    sys.exit(1)

                pin_to_unpin, _ = visible_pins[pos - 1]
                try:
                    pin_service.unpin_node(pin_to_unpin.node_id)
                    print(f"Unpinned position {pos} successfully.")
                    sys.exit(0)
                except PinServiceError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

            # 3. Pins list or activation
            if args.pins is not None or has_filter:
                # Resolve if -p parameter is numeric (activation)
                is_numeric = False
                pos_val = 0
                if isinstance(args.pins, str):
                    try:
                        pos_val = int(args.pins)
                        is_numeric = True
                    except ValueError:
                        pass

                # If -p is present without number (or just filters), list matched pins
                if args.pins is True or not is_numeric or args.pins is None:
                    for idx, (pin, node) in enumerate(visible_pins):
                        visible_pos = idx + 1
                        name = pin.custom_label or node.name
                        workspace = get_originating_workspace(node_service, node)
                        res_type = node.resource_type or node.node_kind
                        target = node.path or ""

                        if args.values:
                            print(target)
                        else:
                            print(
                                f"{visible_pos:<3}{name:<22}{workspace:<11}"
                                f"{res_type:<12}{target}"
                            )
                    sys.exit(0)
                else:
                    # Activate pin by its visible position number
                    if pos_val < 1 or pos_val > len(visible_pins):
                        print(
                            f"Error: No pin found at position {pos_val}.",
                            file=sys.stderr,
                        )
                        sys.exit(1)

                    pin, node = visible_pins[pos_val - 1]

                    # Value access without activation flag
                    if args.value:
                        target = node.path or ""
                        print(target)
                        sys.exit(0)

                    # Directory resource path output activation
                    if (
                        node.node_kind == "resource"
                        and node.resource_type == "directory"
                    ):
                        if not node.path:
                            print(
                                "Error: Directory resource has no path configured.",
                                file=sys.stderr,
                            )
                            sys.exit(1)

                        if args.output:
                            with open(args.output, "w", encoding="utf-8") as f:
                                f.write(node.path)
                        else:
                            print(node.path)
                        sys.exit(0)
                    else:
                        # Non-directory resource action provider activation
                        from pathtree.actions import (
                            DirectoryActionProvider,
                            ResourceActionContext,
                            ResourceActionRegistry,
                        )
                        from pathtree.actions.executable import ExecutableActionProvider
                        from pathtree.actions.file import FileActionProvider
                        from pathtree.actions.script import ScriptActionProvider
                        from pathtree.actions.url import UrlActionProvider

                        action_registry = ResourceActionRegistry()
                        action_registry.register(
                            "resource",
                            "directory",
                            DirectoryActionProvider(node_service),
                        )
                        action_registry.register(
                            "resource", "file", FileActionProvider(node_service)
                        )
                        action_registry.register(
                            "resource", "script", ScriptActionProvider(node_service)
                        )
                        action_registry.register(
                            "resource",
                            "executable",
                            ExecutableActionProvider(node_service),
                        )
                        action_registry.register(
                            "resource", "url", UrlActionProvider(node_service)
                        )

                        provider = action_registry.get_provider(
                            node.node_kind, node.resource_type
                        )
                        if not provider:
                            print(
                                f"Error: No action provider found for node kind "
                                f"'{node.node_kind}' and resource type "
                                f"'{node.resource_type or 'None'}'. Direct CLI "
                                f"activation is not yet supported.",
                                file=sys.stderr,
                            )
                            sys.exit(1)

                        context = ResourceActionContext(
                            node=node,
                            output_path=args.output,
                        )
                        default_action = provider.get_default_action(context)
                        if not default_action:
                            print(
                                "Error: No default action found for "
                                f"node '{node.name}'.",
                                file=sys.stderr,
                            )
                            sys.exit(1)

                        result = provider.execute(default_action.id, context)
                        if not result.success:
                            print(
                                f"Error: {result.error_message or 'Action failed.'}",
                                file=sys.stderr,
                            )
                            sys.exit(1)

                        if result.message:
                            print(result.message)
                        if result.output_value:
                            print(result.output_value)
                        sys.exit(0)

    # Fallback to TUI
    with get_session() as session:
        repository = NodeRepository(session)
        node_service = NodeService(repository)
        from pathtree.ui.app import PathTreeApp

        app = PathTreeApp(node_service=node_service, output=args.output)
        app.run()

    sys.exit(0)


if __name__ == "__main__":
    main()
