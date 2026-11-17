from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config.settings import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode: 生成 SQL 脚本，不连接数据库."""
    url = settings.ACTIVE_DATABASE_URL
    print(f"[alembic] 当前目标（offline）: {settings.ENV} 库")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode: 实际连接数据库执行迁移.

    目标库由 settings.ENV 决定（dev=开发库 / test=测试库），
    切换方式：.env 里改 ENV=test 或环境变量 ENV=test。
    """
    url = settings.ACTIVE_DATABASE_URL
    print(f"[alembic] 当前目标: {settings.ENV} 库")
    config.set_main_option("sqlalchemy.url", url)

    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
