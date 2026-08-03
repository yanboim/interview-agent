"""新增工具调用审计日志。

Revision ID: 20260724_0004
Revises: 20260724_0003
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_0004"
down_revision = "20260724_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_audit_logs",
        sa.Column("audit_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("tool_name", sa.String(length=100), nullable=False),
        sa.Column("input_summary", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("result_summary", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "status IN ('success', 'error', 'denied')",
            name="ck_tool_audit_status",
        ),
        sa.PrimaryKeyConstraint("audit_id"),
    )
    op.create_index(
        "idx_tool_audit_user_created",
        "tool_audit_logs",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_tool_audit_user_created", table_name="tool_audit_logs")
    op.drop_table("tool_audit_logs")
