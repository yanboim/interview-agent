"""为面试新增不可变的简历上下文。

Revision ID: 20260729_0015
Revises: 20260729_0014
"""

from alembic import op
import sqlalchemy as sa


revision = "20260729_0015"
down_revision = "20260729_0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("interviews") as batch:
        batch.add_column(
            sa.Column(
                "source_type",
                sa.String(length=20),
                nullable=False,
                server_default="general",
            )
        )
        batch.add_column(sa.Column("source_resume_id", sa.String(length=128)))
        batch.add_column(sa.Column("source_analysis_id", sa.String(length=128)))
        batch.add_column(sa.Column("source_display_name", sa.String(length=255)))
        batch.add_column(sa.Column("resume_context_json", sa.Text()))
        batch.add_column(
            sa.Column("question_prompt_version", sa.String(length=80))
        )
        batch.create_check_constraint(
            "ck_interviews_source_type",
            "source_type IN ('general', 'resume')",
        )


def downgrade() -> None:
    with op.batch_alter_table("interviews") as batch:
        batch.drop_constraint("ck_interviews_source_type", type_="check")
        batch.drop_column("question_prompt_version")
        batch.drop_column("resume_context_json")
        batch.drop_column("source_display_name")
        batch.drop_column("source_analysis_id")
        batch.drop_column("source_resume_id")
        batch.drop_column("source_type")
