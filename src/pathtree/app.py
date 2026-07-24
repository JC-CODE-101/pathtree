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

    args = parser.parse_args()

    if args.seed_dev:
        with get_session() as session:
            repository = NodeRepository(session)
            seed_development_data(repository)
        print("Development seed data populated successfully.")
        sys.exit(0)

    # CLI Management or Pin List operations
    if args.pin is not None or args.unpin is not None or args.pins is not None:
        with get_session() as session:
            node_repo = NodeRepository(session)
            node_service = NodeService(node_repo)

            from pathtree.database.repository import PinRepository
            from pathtree.services.pin_service import PinService, PinServiceError

            pin_repo = PinRepository(session)
            pin_service = PinService(node_repo, pin_repo)

            # 1. Pin management
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

            # 2. Unpin management
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

                try:
                    pin = pin_service.get_pin_by_position(pos)
                    pin_service.unpin_node(pin.node_id)
                    print(f"Unpinned position {pos} successfully.")
                    sys.exit(0)
                except PinServiceError as e:
                    print(f"Error: {e}", file=sys.stderr)
                    sys.exit(1)

            # 3. Pins list or activation
            if args.pins is not None:
                # Check if pins parameter is numeric (position)
                is_numeric = False
                pos_val = 0
                if isinstance(args.pins, str):
                    try:
                        pos_val = int(args.pins)
                        is_numeric = True
                    except ValueError:
                        pass

                if args.pins is True or not is_numeric:
                    # List pins
                    pins = pin_service.list_pins()
                    for pin in pins:
                        node = node_service.get_node(pin.node_id)
                        if node is None:
                            name = pin.custom_label or "Unknown"
                            workspace = "Unknown"
                        else:
                            name = pin.custom_label or node.name
                            workspace = get_originating_workspace(node_service, node)
                        print(f"{pin.position:<3}{name:<19}{workspace:<12}")
                    sys.exit(0)
                else:
                    # Activate pin by its visible position number
                    try:
                        pin = pin_service.get_pin_by_position(pos_val)
                    except PinServiceError as e:
                        print(f"Error: {e}", file=sys.stderr)
                        sys.exit(1)

                    node = node_service.get_node(pin.node_id)
                    if node is None:
                        print("Error: Pinned node no longer exists.", file=sys.stderr)
                        sys.exit(1)

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
                                f"Error: No default action found for node "
                                f"'{node.name}'.",
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
