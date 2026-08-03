"""新增一次性密码恢复码。

Revision ID: 20260725_0007
Revises: 20260725_0006
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = "20260725_0007"
down_revision = "20260725_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("recovery_code_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "recovery_code_hash")
