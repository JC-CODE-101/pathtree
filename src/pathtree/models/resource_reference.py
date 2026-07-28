import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, ForeignKey
from sqlmodel import Field, SQLModel


class ResourceReference(SQLModel, table=True):
    """Domain model representing a Resource Reference to any other node."""

    __tablename__ = "resource_references"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    reference_node_id: uuid.UUID = Field(
        sa_column=Column(
            ForeignKey("nodes.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    original_node_id: uuid.UUID | None = Field(
        sa_column=Column(
            ForeignKey("nodes.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        )
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
