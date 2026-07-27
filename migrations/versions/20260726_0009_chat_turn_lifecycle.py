"""Add durable chat-turn lifecycle and session ordering.

Revision ID: 20260726_0009
Revises: 20260726_0008
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260726_0009"
down_revision = "20260726_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "next_chat_turn_index",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("active_chat_turn_id", sa.String(length=128), nullable=True),
    )
    op.execute(
        "UPDATE conversations "
        "SET next_chat_turn_index = ("
        "SELECT COUNT(*) + 1 FROM messages "
        "WHERE messages.user_id = conversations.user_id "
        "AND messages.session_id = conversations.session_id "
        "AND messages.role = 'user'"
        ")"
    )
    op.create_table(
        "chat_turns",
        sa.Column("turn_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column("request_content", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("claim_token", sa.String(length=128), nullable=True),
        sa.Column("assistant_content", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "status IN "
            "('pending', 'generating', 'completed', 'failed', 'cancelled')",
            name="ck_chat_turn_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "session_id"],
            ["conversations.user_id", "conversations.session_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("turn_id"),
        sa.UniqueConstraint(
            "user_id",
            "session_id",
            "turn_index",
            name="uq_chat_turn_index",
        ),
        sa.UniqueConstraint(
            "user_id",
            "session_id",
            "idempotency_key",
            name="uq_chat_turn_idempotency",
        ),
    )
    op.create_index(
        "idx_chat_turns_session_status",
        "chat_turns",
        ["user_id", "session_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_chat_turns_session_status", table_name="chat_turns")
    op.drop_table("chat_turns")
    op.drop_column("conversations", "active_chat_turn_id")
    op.drop_column("conversations", "next_chat_turn_index")
