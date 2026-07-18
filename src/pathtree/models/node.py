import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, String
from sqlmodel import Field, SQLModel


class Node(SQLModel, table=True):
    """Combined Persistence & MVP Domain model representing a node in the tree."""

    __tablename__ = "nodes"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    parent_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="nodes.id",
        nullable=True,
        index=True,
    )
    name: str = Field(index=True, nullable=False)
    legacy_node_type: str | None = Field(
        default=None,
        sa_column=Column(
            "node_type",
            String,
            server_default="Folder",
            nullable=False,
        ),
    )  # Legacy database-only column (DEPRECATED - do not use)

    node_kind: str = Field(
        default="resource",
        index=True,
        nullable=False,
    )  # workspace | folder | resource

    resource_type: str | None = Field(
        default=None,
        index=True,
        nullable=True,
    )  # directory | null (for other types in future)

    is_favorite: bool = Field(
        default=False,
        index=True,
        nullable=False,
    )

    is_temporary: bool = Field(
        default=False,
        index=True,
        nullable=False,
    )

    description: str | None = Field(default=None, nullable=True)
    icon: str | None = Field(default=None, nullable=True)
    path: str | None = Field(
        default=None, nullable=True
    )  # Optional filesystem directory path
    sort_order: int = Field(default=0, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), nullable=False
    )
