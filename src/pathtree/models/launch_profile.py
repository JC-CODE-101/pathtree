import json
import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class LaunchProfile(SQLModel, table=True):
    """Domain model representing a launch profile for a Script or Executable."""

    __tablename__ = "launch_profiles"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    profile_node_id: uuid.UUID = Field(
        foreign_key="nodes.id",
        nullable=False,
        index=True,
    )
    workspace_id: uuid.UUID = Field(
        foreign_key="nodes.id",
        nullable=False,
        index=True,
    )
    target_node_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="nodes.id",
        nullable=True,
        index=True,
    )
    target_resource_type: str = Field(
        nullable=False,
    )  # "script" | "executable"
    arguments: str = Field(
        default="[]",
        nullable=False,
    )  # JSON-serialized list of strings
    working_directory_node_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="nodes.id",
        nullable=True,
        index=True,
    )
    terminal_mode: str = Field(
        default="inherit",
        nullable=False,
    )  # "inherit" | "new_terminal"
    status: str = Field(
        default="active",
        nullable=False,
    )  # "active" | "detached" | "invalid"
    previous_target_name: str | None = Field(
        default=None,
        nullable=True,
    )
    previous_target_path: str | None = Field(
        default=None,
        nullable=True,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )

    @property
    def argv(self) -> list[str]:
        """Get arguments as a parsed list of strings."""
        try:
            return json.loads(self.arguments)
        except Exception:
            return []

    @argv.setter
    def argv(self, value: list[str]) -> None:
        """Set arguments as a JSON-serialized list of strings."""
        self.arguments = json.dumps(value)
