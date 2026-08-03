"""新增用户、角色与不透明认证令牌。

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_0002"
down_revision = "20260724_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("password_hash", sa.String(length=128), nullable=False),
        sa.Column("password_salt", sa.String(length=64), nullable=False),
        sa.Column(
            "role",
            sa.String(length=20),
            server_default="user",
            nullable=False,
        ),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "role IN ('user', 'admin')",
            name="ck_users_role",
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("username"),
    )
    op.create_table(
        "auth_tokens",
        sa.Column("token_id", sa.String(length=128), nullable=False),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_type", sa.String(length=20), nullable=False),
        sa.Column("expires_at", sa.String(length=40), nullable=False),
        sa.Column("revoked_at", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint(
            "token_type IN ('access', 'refresh')",
            name="ck_auth_tokens_type",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.user_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("token_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "idx_auth_tokens_user",
        "auth_tokens",
        ["user_id", "token_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_auth_tokens_user", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    op.drop_table("users")
