"""Add real interview transcription and review records.

Revision ID: 20260729_0016
Revises: 20260729_0015
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0016"
down_revision = "20260729_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_reviews",
        sa.Column("review_id", sa.String(length=128), primary_key=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("input_type", sa.String(length=20), nullable=False),
        sa.Column("original_filename", sa.String(length=255)),
        sa.Column("content_type", sa.String(length=120)),
        sa.Column("size_bytes", sa.Integer()),
        sa.Column("sha256", sa.String(length=64)),
        sa.Column("storage_key", sa.String(length=500)),
        sa.Column(
            "external_processing_consent",
            sa.Boolean(),
            nullable=False,
        ),
        sa.Column("consent_at", sa.String(length=40)),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("transcript_json", sa.Text()),
        sa.Column(
            "transcript_revision",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column("confirmed_revision", sa.Integer()),
        sa.Column(
            "create_idempotency_key",
            sa.String(length=128),
            nullable=False,
        ),
        sa.Column(
            "create_request_digest",
            sa.String(length=64),
            nullable=False,
        ),
        sa.Column("analysis_idempotency_key", sa.String(length=128)),
        sa.Column("analysis_request_digest", sa.String(length=64)),
        sa.Column("claim_token", sa.String(length=128)),
        sa.Column("report_json", sa.Text()),
        sa.Column("prompt_version", sa.String(length=80)),
        sa.Column("model_version", sa.String(length=100)),
        sa.Column("error_category", sa.String(length=80)),
        sa.Column("error", sa.Text()),
        sa.Column("processing_started_at", sa.String(length=40)),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.UniqueConstraint(
            "user_id",
            "review_id",
            name="uq_interview_reviews_owner_id",
        ),
        sa.UniqueConstraint(
            "user_id",
            "create_idempotency_key",
            name="uq_interview_reviews_create_idempotency",
        ),
        sa.CheckConstraint(
            "input_type IN ('audio', 'text')",
            name="ck_interview_reviews_input_type",
        ),
        sa.CheckConstraint(
            "status IN ('transcribing', 'awaiting_confirmation', "
            "'analyzing', 'ready', 'failed')",
            name="ck_interview_reviews_status",
        ),
    )
    op.create_index(
        "idx_interview_reviews_owner_updated",
        "interview_reviews",
        ["user_id", "updated_at"],
    )
    op.create_table(
        "interview_review_turns",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("review_id", sa.String(length=128), nullable=False),
        sa.Column("turn_index", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("dimensions_json", sa.Text()),
        sa.Column("strengths_json", sa.Text()),
        sa.Column("weaknesses_json", sa.Text()),
        sa.Column("feedback", sa.Text()),
        sa.Column("improved_answer", sa.Text()),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id", "review_id"],
            ["interview_reviews.user_id", "interview_reviews.review_id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_id",
            "review_id",
            "turn_index",
            name="uq_interview_review_turns_index",
        ),
    )
    op.create_index(
        "idx_interview_review_turns_owner_review",
        "interview_review_turns",
        ["user_id", "review_id", "turn_index"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_interview_review_turns_owner_review",
        table_name="interview_review_turns",
    )
    op.drop_table("interview_review_turns")
    op.drop_index(
        "idx_interview_reviews_owner_updated",
        table_name="interview_reviews",
    )
    op.drop_table("interview_reviews")
