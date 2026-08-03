"""新增管理员审计与执行追踪。

Revision ID: 20260728_0012
Revises: 20260728_0011
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_0012"
down_revision = "20260728_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tool_audit_logs") as batch:
        batch.add_column(sa.Column("request_id", sa.String(128)))
        batch.add_column(sa.Column("interaction_type", sa.String(30)))
        batch.add_column(sa.Column("interaction_id", sa.String(256)))

    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(128), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("actor_user_id", sa.String(128)),
        sa.Column("actor_username", sa.String(100)),
        sa.Column("actor_role", sa.String(20)),
        sa.Column("action", sa.String(160), nullable=False),
        sa.Column("resource_type", sa.String(80), nullable=False),
        sa.Column("resource_id", sa.String(256)),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('success', 'error', 'denied')",
            name="ck_audit_events_outcome",
        ),
    )
    op.create_index("idx_audit_events_created", "audit_events", ["created_at"])
    op.create_index(
        "idx_audit_events_actor_created",
        "audit_events",
        ["actor_user_id", "created_at"],
    )
    op.create_index(
        "idx_audit_events_action_created",
        "audit_events",
        ["action", "created_at"],
    )

    op.create_table(
        "execution_traces",
        sa.Column("trace_id", sa.String(128), primary_key=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("interaction_type", sa.String(30), nullable=False),
        sa.Column("interaction_id", sa.String(256), nullable=False),
        sa.Column("stage", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("duration_ms", sa.Integer()),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index(
        "idx_execution_trace_interaction",
        "execution_traces",
        ["interaction_type", "interaction_id", "created_at"],
    )
    op.create_index(
        "idx_execution_trace_request",
        "execution_traces",
        ["request_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_execution_trace_request",
        table_name="execution_traces",
    )
    op.drop_index(
        "idx_execution_trace_interaction",
        table_name="execution_traces",
    )
    op.drop_table("execution_traces")
    op.drop_index("idx_audit_events_action_created", table_name="audit_events")
    op.drop_index("idx_audit_events_actor_created", table_name="audit_events")
    op.drop_index("idx_audit_events_created", table_name="audit_events")
    op.drop_table("audit_events")
    with op.batch_alter_table("tool_audit_logs") as batch:
        batch.drop_column("interaction_id")
        batch.drop_column("interaction_type")
        batch.drop_column("request_id")
