"""Add durable chat context summary.

Revision ID: 20260726_0010
Revises: 20260726_0009
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260726_0010"
down_revision = "20260726_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "chat_summary",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "chat_summary_through_message_id",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "conversations",
        "chat_summary_through_message_id",
    )
    op.drop_column("conversations", "chat_summary")
