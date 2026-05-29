"""
Alembic 環境設定 - 用 sync engine（Alembic 不支援 async）。
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

# 把 api 加入 sys.path，才能 import api.database
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.database import Base  # noqa: E402

# 載入所有 models 讓 Alembic 偵測到（Week 1 開始加）
# from api.models import models, posts, sentiments  # noqa: F401

config = context.config

# 從環境變數讀 DATABASE_URL_SYNC（不要 hardcode）
database_url = os.environ.get(
    "DATABASE_URL_SYNC",
    "postgresql://pulse:pulse@localhost:5432/pulse",
)
config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
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
