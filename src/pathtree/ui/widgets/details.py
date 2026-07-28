"""Widget displaying detailed information about the highlighted node."""

from textual.widgets import Static

from pathtree.models.node import Node


class NodeDetailsPanel(Static):
    """Widget displaying detailed information about the highlighted node."""

    def __init__(self, **kwargs) -> None:
        """Initialize the NodeDetailsPanel with default text."""
        super().__init__("No node selected.", **kwargs)

    def update_node(
        self, node: Node | None, empty_message: str = "No node selected."
    ) -> None:
        """Update the panel with details of the provided node.

        Args:
            node: The Node object to display, or None if no node is selected.
            empty_message: Custom message to display if node is None.
        """
        if node is None:
            self.update(empty_message)
            return

        if node.node_kind == "resource" and node.resource_type == "multi_launcher":
            from pathtree.database.repository import (
                LaunchProfileRepository,
                MultiLauncherRepository,
            )
            from pathtree.services.launch_profile_service import (
                LaunchProfileService,
            )
            from pathtree.services.multi_launcher_service import (
                MultiLauncherService,
            )

            try:
                session = self.screen.node_service.repository.session
                lp_repo = LaunchProfileRepository(session)
                lp_service = LaunchProfileService(self.screen.node_service, lp_repo)
                ml_repo = MultiLauncherRepository(session)
                ml_service = MultiLauncherService(
                    self.screen.node_service, lp_service, ml_repo
                )

                launcher = ml_service.get_launcher_for_node(node.id)
                items = ml_repo.list_items_for_launcher(launcher.id)

                total_count = len(items)
                enabled_count = sum(1 for item in items if item.enabled)

                enabled_items = [it for it in items if it.enabled]
                total_delay = sum(
                    it.delay_ms
                    for idx, it in enumerate(enabled_items)
                    if idx < len(enabled_items) - 1
                )

                summary_lines = []
                for idx, item in enumerate(items):
                    try:
                        profile = lp_service.get_profile(item.launch_profile_id)
                        p_node = self.screen.node_service.get_node(
                            profile.profile_node_id
                        )
                        p_name = p_node.name if p_node else "Unknown"
                    except Exception:
                        p_name = "Unknown"

                    if not item.enabled:
                        summary_lines.append(f"  {idx + 1}. {p_name} \\[disabled]")
                    elif item.delay_ms > 0:
                        summary_lines.append(
                            f"  {idx + 1}. {p_name} \\[{item.delay_ms} ms]"
                        )
                    else:
                        summary_lines.append(f"  {idx + 1}. {p_name}")

                summary_str = (
                    "\n".join(summary_lines)
                    if summary_lines
                    else "  No profiles added."
                )

                ws_name = "N/A"
                ws_node = self.screen.node_service.get_node(launcher.workspace_id)
                if ws_node:
                    ws_name = ws_node.name

                content = (
                    f"[bold]Name:[/bold] {node.name}\n"
                    f"[bold]Type:[/bold] multi_launcher\n"
                    f"[bold]Workspace:[/bold] {ws_name}\n"
                    f"[bold]Profiles:[/bold] {total_count}\n"
                    f"[bold]Enabled:[/bold] {enabled_count}\n"
                    f"[bold]Total Delay:[/bold] {total_delay} ms\n"
                    f"[bold]Description:[/bold] {node.description or 'N/A'}\n\n"
                    f"[bold]Execution:[/bold]\n{summary_str}"
                )
                self.update(content)
                return
            except Exception:
                pass

        name = node.name
        node_type = node.resource_type if node.resource_type else node.node_kind
        path = node.path if node.path else "N/A"
        description = node.description if node.description else "N/A"

        from pathtree.utils.icons import icon_registry

        icon = icon_registry.get_icon(node)

        content = (
            f"[bold]Name:[/bold] {name}\n"
            f"[bold]Type:[/bold] {node_type}\n"
            f"[bold]Icon:[/bold] {icon}\n"
            f"[bold]Path:[/bold] {path}\n"
            f"[bold]Description:[/bold] {description}"
        )
        self.update(content)

    def update_error(self, message: str) -> None:
        """Display an error message inside the panel.

        Args:
            message: The error message to display.
        """
        self.update(f"[bold red]Error:[/bold red] {message}")
