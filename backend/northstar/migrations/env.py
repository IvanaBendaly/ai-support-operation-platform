from alembic import context

from northstar import models  # noqa: F401 -- register domain metadata
from northstar.cases import models as case_models  # noqa: F401
from northstar.config import load_settings
from northstar.db import Base, make_engine
from northstar.retrieval import models as knowledge_models  # noqa: F401

if context.is_offline_mode():
    context.configure(
        url=load_settings().database_url.get_secret_value(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = make_engine(load_settings())
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            # SQLite batch DDL recreates referenced tables. Disable checks only on
            # this migration connection, then validate all references before commit.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            connection.commit()
            try:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                context.configure(
                    connection=connection, target_metadata=Base.metadata, transactional_ddl=True
                )
                context.run_migrations()
                if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
                    raise RuntimeError("Migration would leave invalid foreign keys.")
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        else:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    engine.dispose()
