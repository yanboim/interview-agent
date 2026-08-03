"""新增应用拥有的可恢复 Agent run 与 step。

Revision ID: 20260731_0020
Revises: 20260731_0019
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_0020"
down_revision = "20260731_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_runs",
        sa.Column("run_id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("run_type", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("proposal_json", sa.Text()),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "status IN ('proposed', 'awaiting_confirmation', 'running', "
            "'completed', 'failed', 'cancelled')",
            name="ck_agent_runs_status",
        ),
        sa.UniqueConstraint(
            "user_id", "run_type", "idempotency_key",
            name="uq_agent_runs_idempotency",
        ),
    )
    op.create_index(
        "idx_agent_runs_owner_status", "agent_runs", ["user_id", "status"]
    )
    op.create_table(
        "agent_steps",
        sa.Column("step_id", sa.String(128), primary_key=True),
        sa.Column("run_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("step_key", sa.String(80), nullable=False),
        sa.Column("step_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("idempotency_key", sa.String(160), nullable=False),
        sa.Column("input_digest", sa.String(64), nullable=False),
        sa.Column("claim_owner", sa.String(128)),
        sa.Column("claimed_at", sa.String(40)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.Text()),
        sa.Column("error_code", sa.String(80)),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "step_type IN ('read', 'model', 'command')",
            name="ck_agent_steps_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'completed', 'failed', 'skipped')",
            name="ck_agent_steps_status",
        ),
        sa.UniqueConstraint("run_id", "step_key", name="uq_agent_steps_run_key"),
        sa.UniqueConstraint(
            "user_id", "idempotency_key", name="uq_agent_steps_idempotency"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.run_id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_agent_steps_run_status", "agent_steps", ["run_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("idx_agent_steps_run_status", table_name="agent_steps")
    op.drop_table("agent_steps")
    op.drop_index("idx_agent_runs_owner_status", table_name="agent_runs")
    op.drop_table("agent_runs")
