"""Alembic environment — connection string from Settings.db_url, schema from ORM Base.metadata.

At runtime: `alembic upgrade head`. The connection comes from the ETKI_DB_URL environment
variable (sqlite or postgresql+psycopg). The core never knows the concrete DB; Alembic binds here.
"""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from etki.config import Settings
from etki.persistence import models  # noqa: F401 — registers tables on the metadata
from etki.persistence.db import Base
from sqlalchemy import engine_from_config, pool

config = context.config
config.set_main_option("sqlalchemy.url", Settings().db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,  # batch mode for SQLite ALTER limitations
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
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
