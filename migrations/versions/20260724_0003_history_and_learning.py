"""新增面试归档与学习任务。

Revision ID: 20260724_0003
Revises: 20260724_0002
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_0003"
down_revision = "20260724_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interviews",
        sa.Column("archived_at", sa.String(length=40), nullable=True),
    )
    op.create_table(
        "learning_tasks",
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("source_interview_id", sa.String(length=128), nullable=True),
        sa.Column("dimension", sa.String(length=100), nullable=False),
        sa.Column("weakness", sa.String(length=300), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="todo",
            nullable=False,
        ),
        sa.Column("due_at", sa.String(length=40), nullable=False),
        sa.Column(
            "review_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("last_reviewed_at", sa.String(length=40), nullable=True),
        sa.Column("next_review_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "status IN ('todo', 'in_progress', 'completed')",
            name="ck_learning_tasks_status",
        ),
        sa.PrimaryKeyConstraint("task_id"),
    )
    op.create_index(
        "idx_learning_tasks_user_status",
        "learning_tasks",
        ["user_id", "status", "due_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_learning_tasks_user_status",
        table_name="learning_tasks",
    )
    op.drop_table("learning_tasks")
    op.drop_column("interviews", "archived_at")
