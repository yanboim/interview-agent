"""持久化产品档案、引用、答题尝试与事件。

Revision ID: 20260725_0005
Revises: 20260724_0004
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260725_0005"
down_revision = "20260724_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("metadata_json", sa.Text(), nullable=True))
    op.add_column(
        "interview_turns",
        sa.Column("reference_answer", sa.Text(), nullable=True),
    )
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("target_role", sa.String(length=100), nullable=False),
        sa.Column("experience_level", sa.String(length=30), nullable=False),
        sa.Column(
            "focus_areas",
            sa.String(length=300),
            server_default="",
            nullable=False,
        ),
        sa.Column("interview_date", sa.String(length=40), nullable=True),
        sa.Column(
            "job_description",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "interview_answer_attempts",
        sa.Column("attempt_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("interview_id", sa.String(length=128), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("attempt_index", sa.Integer(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("dimensions_json", sa.Text(), nullable=False),
        sa.Column("strengths_json", sa.Text(), nullable=False),
        sa.Column("weaknesses_json", sa.Text(), nullable=False),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "interview_id"],
            ["interviews.user_id", "interviews.interview_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("attempt_id"),
        sa.UniqueConstraint(
            "user_id",
            "interview_id",
            "turn_index",
            "attempt_index",
            name="uq_interview_answer_attempt",
        ),
    )
    op.create_index(
        "idx_interview_attempts_turn",
        "interview_answer_attempts",
        ["user_id", "interview_id", "turn_index"],
    )
    op.create_table(
        "product_events",
        sa.Column("event_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("session_id", sa.String(length=128), nullable=True),
        sa.Column("event_name", sa.String(length=100), nullable=False),
        sa.Column(
            "properties_json",
            sa.Text(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "idx_product_events_user_created",
        "product_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_product_events_user_created", table_name="product_events")
    op.drop_table("product_events")
    op.drop_index(
        "idx_interview_attempts_turn",
        table_name="interview_answer_attempts",
    )
    op.drop_table("interview_answer_attempts")
    op.drop_table("user_profiles")
    op.drop_column("interview_turns", "reference_answer")
    op.drop_column("messages", "metadata_json")
