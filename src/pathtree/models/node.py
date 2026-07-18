import uuid
from datetime import UTC, datetime

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
    node_type: str = Field(
        default="Folder",
        index=True,
        nullable=False,
    )  # Workspace or Folder
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
