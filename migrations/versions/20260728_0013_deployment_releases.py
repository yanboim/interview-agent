"""新增管理员部署发版记录簿。

Revision ID: 20260728_0013
Revises: 20260728_0012
Create Date: 2026-07-28
"""

from alembic import op
import sqlalchemy as sa


revision = "20260728_0013"
down_revision = "20260728_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "deployment_releases",
        sa.Column("release_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("environment", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=True),
        sa.Column("changes_json", sa.Text(), server_default="[]", nullable=False),
        sa.Column(
            "verification_json",
            sa.Text(),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("app_image", sa.String(length=200), nullable=True),
        sa.Column("worker_image", sa.String(length=200), nullable=True),
        sa.Column("migration_revision", sa.String(length=64), nullable=True),
        sa.Column("recovery_point", sa.String(length=200), nullable=True),
        sa.Column("triggered_by", sa.String(length=100), nullable=False),
        sa.Column("started_at", sa.String(length=40), nullable=False),
        sa.Column("completed_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "environment IN ('canary', 'production')",
            name="ck_deployment_releases_environment",
        ),
        sa.CheckConstraint(
            "status IN ('deploying', 'succeeded', 'failed', 'rolled_back')",
            name="ck_deployment_releases_status",
        ),
        sa.PrimaryKeyConstraint("release_id"),
    )
    op.create_index(
        "idx_deployment_releases_environment_completed",
        "deployment_releases",
        ["environment", "completed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_deployment_releases_environment_completed",
        table_name="deployment_releases",
    )
    op.drop_table("deployment_releases")
