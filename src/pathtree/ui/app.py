"""Main Textual application for PathTree."""

from textual.app import App

from pathtree.services.node_service import NodeService
from pathtree.ui.screens.main import MainScreen


class PathTreeApp(App[None]):
    """Main Textual application for PathTree."""

    TITLE = "PathTree"

    def __init__(
        self, node_service: NodeService, output: str | None = None, **kwargs
    ) -> None:
        """Initialize PathTreeApp with service and output details."""
        super().__init__(**kwargs)
        self.node_service = node_service
        self.output_path = output

    def on_mount(self) -> None:
        """Mount the main screen when the application starts."""
        self.push_screen(MainScreen(self.node_service, self.output_path))

    def action_quit(self) -> None:
        """Quit the application safely with exit code 0."""
        self.exit(code=0)
