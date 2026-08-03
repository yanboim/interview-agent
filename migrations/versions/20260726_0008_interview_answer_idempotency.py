"""新增可恢复的面试答题提交生命周期（幂等领取/完成/失败）。

Revision ID: 20260726_0008
Revises: 20260725_0007
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = "20260726_0008"
down_revision = "20260725_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_turns",
        sa.Column(
            "submission_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "interview_turns",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "interview_turns",
        sa.Column("answer_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "interview_turns",
        sa.Column("claim_token", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "interview_turns",
        sa.Column("result_json", sa.Text(), nullable=True),
    )
    op.add_column(
        "interview_turns",
        sa.Column("submission_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "interview_turns",
        sa.Column("processing_started_at", sa.String(length=40), nullable=True),
    )
    op.execute(
        "UPDATE interview_turns "
        "SET submission_status = 'completed' "
        "WHERE answer IS NOT NULL"
    )
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.create_check_constraint(
            "ck_interview_turn_submission_status",
            "submission_status IN "
            "('pending', 'generating', 'completed', 'failed')",
        )
        batch_op.create_unique_constraint(
            "uq_interview_turn_idempotency",
            ["user_id", "interview_id", "idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("interview_turns") as batch_op:
        batch_op.drop_constraint(
            "uq_interview_turn_idempotency",
            type_="unique",
        )
        batch_op.drop_constraint(
            "ck_interview_turn_submission_status",
            type_="check",
        )
    op.drop_column("interview_turns", "processing_started_at")
    op.drop_column("interview_turns", "submission_error")
    op.drop_column("interview_turns", "result_json")
    op.drop_column("interview_turns", "claim_token")
    op.drop_column("interview_turns", "answer_digest")
    op.drop_column("interview_turns", "idempotency_key")
    op.drop_column("interview_turns", "submission_status")
