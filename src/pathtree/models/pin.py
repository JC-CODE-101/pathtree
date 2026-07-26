import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class Pin(SQLModel, table=True):
    """Domain model representing a global shortcut pin for a Node."""

    __tablename__ = "pins"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    node_id: uuid.UUID = Field(
        foreign_key="nodes.id",
        nullable=False,
        index=True,
    )
    position: int = Field(
        index=True,
        nullable=False,
    )
    custom_label: str | None = Field(
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
