import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class MultiLauncher(SQLModel, table=True):
    """Domain model representing a Multi Launcher."""

    __tablename__ = "multi_launchers"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    launcher_node_id: uuid.UUID = Field(
        foreign_key="nodes.id",
        nullable=False,
        index=True,
    )
    workspace_id: uuid.UUID = Field(
        foreign_key="nodes.id",
        nullable=False,
        index=True,
    )
    name: str = Field(nullable=False)
    description: str | None = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )


class MultiLauncherItem(SQLModel, table=True):
    """Domain model representing an item in a Multi Launcher."""

    __tablename__ = "multi_launcher_items"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    multi_launcher_id: uuid.UUID = Field(
        foreign_key="multi_launchers.id",
        nullable=False,
        index=True,
    )
    launch_profile_id: uuid.UUID = Field(
        foreign_key="launch_profiles.id",
        nullable=False,
        index=True,
    )
    position: int = Field(nullable=False)
    enabled: bool = Field(default=True, nullable=False)
    delay_ms: int = Field(default=0, nullable=False)
