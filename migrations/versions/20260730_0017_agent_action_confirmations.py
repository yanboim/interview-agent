"""新增所有者绑定的 Agent 动作确认。

Revision ID: 20260730_0017
Revises: 20260729_0016
"""

from alembic import op
import sqlalchemy as sa


revision = "20260730_0017"
down_revision = "20260729_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_action_confirmations",
        sa.Column("confirmation_id", sa.String(length=128), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("payload_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("result_json", sa.Text()),
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.Column("consumed_at", sa.String(length=40)),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'applied', 'cancelled', 'expired')",
            name="ck_agent_action_confirmations_status",
        ),
    )
    op.create_index(
        "idx_agent_action_confirmations_owner_status",
        "agent_action_confirmations",
        ["user_id", "status", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_agent_action_confirmations_owner_status",
        table_name="agent_action_confirmations",
    )
    op.drop_table("agent_action_confirmations")
