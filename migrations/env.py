"""Alembic 迁移环境：从应用配置解析数据库 URL 并驱动离线/在线迁移。"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.database import metadata, normalize_database_url


config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

settings = get_settings()
database_url = normalize_database_url(
    settings.database_url or settings.conversation_db_path
)
config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
target_metadata = metadata


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本而不连接数据库（``alembic upgrade --sql``）。"""
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库并在单事务中执行迁移（默认 ``alembic upgrade``）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
