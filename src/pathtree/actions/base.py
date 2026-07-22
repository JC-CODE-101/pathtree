"""Base models, protocols, and context for the PathTree action framework."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pathtree.models.node import Node


@dataclass(frozen=True)
class ResourceAction:
    """Represents a performable action on a resource."""

    id: str
    label: str
    description: str | None = None
    is_default: bool = False
    is_enabled: bool = True


@dataclass(frozen=True)
class ResourceActionContext:
    """The context in which a resource action is executed."""

    node: Node
    resolved_path: str | None = None
    output_path: str | None = None


@dataclass(frozen=True)
class ResourceActionResult:
    """The result of executing a resource action."""

    success: bool
    exit_app: bool = False
    output_value: str | None = None
    message: str | None = None
    error_message: str | None = None


@runtime_checkable
class ResourceActionProvider(Protocol):
    """Protocol defining the interface for resource action providers."""

    @property
    def resource_type(self) -> str | None:
        """The supported resource type, e.g., 'directory'."""
        ...

    def get_available_actions(
        self, context: ResourceActionContext
    ) -> list[ResourceAction]:
        """Returns available actions for the resource."""
        ...

    def get_default_action(
        self, context: ResourceActionContext
    ) -> ResourceAction | None:
        """Returns the default action for the resource."""
        ...

    def execute(
        self, action_id: str, context: ResourceActionContext
    ) -> ResourceActionResult:
        """Executes the selected action."""
        ...
