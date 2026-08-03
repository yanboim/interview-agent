"""为生成产物持久化提示词、schema 与模型版本。

Revision ID: 20260731_0018
Revises: 20260730_0017
"""

from alembic import op
import sqlalchemy as sa


revision = "20260731_0018"
down_revision = "20260730_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interviews", sa.Column("question_schema_version", sa.String(80)))
    op.add_column("interviews", sa.Column("question_model_version", sa.String(100)))
    op.add_column(
        "resume_analyses",
        sa.Column(
            "schema_version",
            sa.String(80),
            nullable=False,
            server_default="resume-analysis-v1",
        ),
    )
    op.add_column("interview_reviews", sa.Column("schema_version", sa.String(80)))
    op.add_column(
        "interview_turns", sa.Column("assessment_prompt_version", sa.String(80))
    )
    op.add_column(
        "interview_turns", sa.Column("assessment_schema_version", sa.String(80))
    )
    op.add_column(
        "interview_turns", sa.Column("assessment_model_version", sa.String(100))
    )
    op.add_column(
        "interview_answer_attempts", sa.Column("prompt_version", sa.String(80))
    )
    op.add_column(
        "interview_answer_attempts", sa.Column("schema_version", sa.String(80))
    )
    op.add_column(
        "interview_answer_attempts", sa.Column("model_version", sa.String(100))
    )
    op.add_column("execution_traces", sa.Column("prompt_version", sa.String(80)))
    op.add_column("execution_traces", sa.Column("schema_version", sa.String(80)))
    op.add_column("execution_traces", sa.Column("model_version", sa.String(100)))


def downgrade() -> None:
    op.drop_column("execution_traces", "model_version")
    op.drop_column("execution_traces", "schema_version")
    op.drop_column("execution_traces", "prompt_version")
    op.drop_column("interview_answer_attempts", "model_version")
    op.drop_column("interview_answer_attempts", "schema_version")
    op.drop_column("interview_answer_attempts", "prompt_version")
    op.drop_column("interview_turns", "assessment_model_version")
    op.drop_column("interview_turns", "assessment_schema_version")
    op.drop_column("interview_turns", "assessment_prompt_version")
    op.drop_column("interview_reviews", "schema_version")
    op.drop_column("resume_analyses", "schema_version")
    op.drop_column("interviews", "question_model_version")
    op.drop_column("interviews", "question_schema_version")
