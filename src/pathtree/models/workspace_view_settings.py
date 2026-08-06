import uuid
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class WorkspaceViewSettings(SQLModel, table=True):
    """Domain model representing per-workspace View settings."""

    __tablename__ = "workspace_view_settings"

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        nullable=False,
    )
    workspace_id: uuid.UUID = Field(
        foreign_key="nodes.id",
        nullable=False,
        index=True,
        unique=True,
    )
    current_mode: str = Field(default="all", nullable=False)  # 'all' | 'filter'
    last_filter_mask: int = Field(default=0, nullable=False)
    hide_empty_sections: bool = Field(default=False, nullable=False)
    show_system: bool = Field(default=True, nullable=False)
    show_custom: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        nullable=False,
    )
