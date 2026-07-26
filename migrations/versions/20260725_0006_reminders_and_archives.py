"""Add reminder preferences and conversation archives.

Revision ID: 20260725_0006
Revises: 20260725_0005
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260725_0006"
down_revision = "20260725_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("archived_at", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "reminder_enabled",
            sa.Boolean(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "reminder_time",
            sa.String(length=5),
            server_default="09:00",
            nullable=False,
        ),
    )
    op.add_column(
        "user_profiles",
        sa.Column(
            "reminder_timezone",
            sa.String(length=64),
            server_default="UTC",
            nullable=False,
        ),
    )
    op.create_index(
        "idx_conversations_user_archived_updated",
        "conversations",
        ["user_id", "archived_at", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_conversations_user_archived_updated",
        table_name="conversations",
    )
    op.drop_column("user_profiles", "reminder_timezone")
    op.drop_column("user_profiles", "reminder_time")
    op.drop_column("user_profiles", "reminder_enabled")
    op.drop_column("conversations", "archived_at")
