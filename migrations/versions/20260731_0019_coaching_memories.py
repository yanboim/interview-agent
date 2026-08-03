"""新增所有者范围内已确认的教练记忆。

Revision ID: 20260731_0019
Revises: 20260731_0018
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_0019"
down_revision = "20260731_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coaching_memories",
        sa.Column("memory_id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="proposed"),
        sa.Column("source_type", sa.String(40), nullable=False, server_default="user"),
        sa.Column("source_id", sa.String(128)),
        sa.Column("source_revision", sa.Integer()),
        sa.Column("expires_at", sa.String(40)),
        sa.Column("confirmed_at", sa.String(40)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "kind IN ('fact', 'preference', 'goal', 'observation')",
            name="ck_coaching_memories_kind",
        ),
        sa.CheckConstraint(
            "status IN ('proposed', 'confirmed', 'rejected')",
            name="ck_coaching_memories_status",
        ),
    )
    op.create_index(
        "idx_coaching_memories_owner_status",
        "coaching_memories",
        ["user_id", "status", "updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_coaching_memories_owner_status",
        table_name="coaching_memories",
    )
    op.drop_table("coaching_memories")
