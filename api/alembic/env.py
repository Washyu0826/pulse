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

# 載入所有 models 讓 Alembic autogenerate 偵測到全部資料表。
# api.models.__init__ 已 re-export 所有 model，import 套件即可（不會漏表）。
import api.models  # noqa: F401,E402
from api.config import settings  # noqa: E402
from api.database import Base  # noqa: E402

config = context.config

# DATABASE_URL_SYNC 優先吃環境變數（CI / Docker），否則退回 settings（本地）。
database_url = os.environ.get("DATABASE_URL_SYNC", settings.database_url_sync)
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
        compare_type=True,
        compare_server_default=True,
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
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
