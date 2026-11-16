from logging.config import fileConfig

from alembic import context

from app import models  # noqa: F401 - registers every table on Base.metadata
from app.db import Base, get_engine

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logging", True):
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata

# Managed by hand in migrations: the FTS5 table (and its shadow tables) and expression indexes.
EXPRESSION_INDEXES = {"ix_tools_status_score", "ix_tools_status_published", "ix_tools_status_stars"}


def include_object(obj, name, type_, reflected, compare_to) -> bool:
    if type_ == "table" and name and name.startswith("tool_search"):
        return False
    return not (type_ == "index" and name in EXPRESSION_INDEXES)


def run_migrations_online() -> None:
    connectable = config.attributes.get("connection") or get_engine()
    if hasattr(connectable, "connect"):
        with connectable.connect() as connection:
            _run(connection)
    else:
        _run(connectable)


def _run(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
