"""Add user-owned resume documents and analysis versions.

Revision ID: 20260729_0014
Revises: 20260728_0013
Create Date: 2026-07-29
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0014"
down_revision = "20260728_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resume_documents",
        sa.Column("resume_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="uploaded",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "status IN ('uploaded', 'processing', 'ready', 'failed')",
            name="ck_resume_documents_status",
        ),
        sa.PrimaryKeyConstraint("resume_id"),
        sa.UniqueConstraint(
            "user_id",
            "resume_id",
            name="uq_resume_documents_owner",
        ),
        sa.UniqueConstraint(
            "user_id",
            "idempotency_key",
            name="uq_resume_upload_idempotency",
        ),
    )
    op.create_index(
        "idx_resume_documents_user_updated",
        "resume_documents",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "resume_analyses",
        sa.Column("analysis_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("resume_id", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("request_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column("claim_token", sa.String(length=128), nullable=True),
        sa.Column(
            "job_description",
            sa.Text(),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "target_role",
            sa.String(length=100),
            server_default="",
            nullable=False,
        ),
        sa.Column(
            "experience_level",
            sa.String(length=30),
            server_default="",
            nullable=False,
        ),
        sa.Column("parsed_text", sa.Text(), nullable=True),
        sa.Column("report_json", sa.Text(), nullable=True),
        sa.Column("draft_json", sa.Text(), nullable=True),
        sa.Column(
            "warnings_json",
            sa.Text(),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "revision",
            sa.Integer(),
            server_default="1",
            nullable=False,
        ),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column(
            "model_version",
            sa.String(length=100),
            server_default="",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'ready', 'failed')",
            name="ck_resume_analyses_status",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "resume_id"],
            ["resume_documents.user_id", "resume_documents.resume_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("analysis_id"),
        sa.UniqueConstraint(
            "user_id",
            "resume_id",
            "idempotency_key",
            name="uq_resume_analysis_idempotency",
        ),
    )
    op.create_index(
        "idx_resume_analyses_resume_created",
        "resume_analyses",
        ["user_id", "resume_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_resume_analyses_resume_created",
        table_name="resume_analyses",
    )
    op.drop_table("resume_analyses")
    op.drop_index(
        "idx_resume_documents_user_updated",
        table_name="resume_documents",
    )
    op.drop_table("resume_documents")
