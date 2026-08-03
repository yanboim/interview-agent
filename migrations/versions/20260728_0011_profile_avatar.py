"""新增账号档案头像。

Revision ID: 20260728_0011
Revises: 20260726_0010
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_0011"
down_revision = "20260726_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_profiles",
        sa.Column("avatar_data_url", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_profiles", "avatar_data_url")
