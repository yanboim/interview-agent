"""Add durable feedback and outcome-aware learning state.

Revision ID: 20260731_0021
Revises: 20260731_0020
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_0021"
down_revision = "20260731_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("learning_tasks") as batch:
        batch.add_column(sa.Column("recall_outcome", sa.String(20)))
        batch.add_column(sa.Column("difficulty_rating", sa.Integer()))
        batch.add_column(sa.Column("lapse_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("review_confidence", sa.Float(), nullable=False, server_default="0.5"))
        batch.create_check_constraint(
            "ck_learning_tasks_recall_outcome",
            "recall_outcome IS NULL OR recall_outcome IN ('remembered', 'partial', 'forgotten')",
        )
        batch.create_check_constraint(
            "ck_learning_tasks_difficulty",
            "difficulty_rating IS NULL OR difficulty_rating BETWEEN 1 AND 5",
        )
    op.create_table(
        "assistant_feedback",
        sa.Column("feedback_id", sa.String(128), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("turn_id", sa.String(128), nullable=False),
        sa.Column("rating", sa.String(10), nullable=False),
        sa.Column("reason_code", sa.String(40)),
        sa.Column("comment", sa.Text()),
        sa.Column("prompt_version", sa.String(80)),
        sa.Column("schema_version", sa.String(80)),
        sa.Column("model_version", sa.String(100)),
        sa.Column("source_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.CheckConstraint("rating IN ('up', 'down')", name="ck_assistant_feedback_rating"),
        sa.UniqueConstraint("user_id", "turn_id", name="uq_assistant_feedback_turn"),
    )
    op.create_index(
        "idx_assistant_feedback_owner_rating", "assistant_feedback",
        ["user_id", "rating", "updated_at"],
    )
    op.create_table(
        "evaluation_candidates",
        sa.Column("candidate_id", sa.String(128), primary_key=True),
        sa.Column("feedback_id", sa.String(128), nullable=False, unique=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending_privacy_review"),
        sa.Column("reviewed_by", sa.String(128)),
        sa.Column("reviewed_at", sa.String(40)),
        sa.Column("approved_payload_json", sa.Text()),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending_privacy_review', 'approved', 'rejected')",
            name="ck_evaluation_candidates_status",
        ),
    )
    op.create_index("idx_evaluation_candidates_status", "evaluation_candidates", ["status"])


def downgrade() -> None:
    op.drop_index("idx_evaluation_candidates_status", table_name="evaluation_candidates")
    op.drop_table("evaluation_candidates")
    op.drop_index("idx_assistant_feedback_owner_rating", table_name="assistant_feedback")
    op.drop_table("assistant_feedback")
    with op.batch_alter_table("learning_tasks") as batch:
        batch.drop_constraint("ck_learning_tasks_difficulty", type_="check")
        batch.drop_constraint("ck_learning_tasks_recall_outcome", type_="check")
        batch.drop_column("review_confidence")
        batch.drop_column("lapse_count")
        batch.drop_column("difficulty_rating")
        batch.drop_column("recall_outcome")
