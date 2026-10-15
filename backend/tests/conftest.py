import os
from datetime import date

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect

from northstar.config import Settings
from northstar.db import Base, make_engine, session_factory
from northstar.domain import BusinessService
from northstar.seed import seed

AS_OF = date(2026, 10, 12)


@pytest.fixture(scope="session")
def postgres_engine():
    url = os.getenv("NORTHSTAR_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set NORTHSTAR_TEST_DATABASE_URL to an empty disposable PostgreSQL database")
    settings = Settings(_env_file=None, environment="test", database_url=url)
    engine = make_engine(settings)
    assert engine.dialect.name == "postgresql", "Integration database must be PostgreSQL"
    assert not inspect(engine).get_table_names(), "Refusing to modify a nonempty test database"
    with pytest.MonkeyPatch.context() as environment:
        environment.setenv("NORTHSTAR_ENVIRONMENT", "test")
        environment.setenv("NORTHSTAR_DATABASE_URL", url)
        command.upgrade(Config("alembic.ini"), "head")
        yield engine
        command.downgrade(Config("alembic.ini"), "base")
        # Remove only Alembic's empty bookkeeping table, created by this fixture.
        with engine.begin() as connection:
            from sqlalchemy import text

            connection.execute(text("DROP TABLE alembic_version"))
    engine.dispose()


@pytest.fixture
def postgres_business(postgres_engine):
    sessions = session_factory(postgres_engine)
    with sessions.begin() as session:
        seed(session, AS_OF)
    yield sessions, BusinessService(sessions, today=lambda: AS_OF)
    with postgres_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())


@pytest.fixture
def business():
    settings = Settings(
        _env_file=None, environment="test", database_url="sqlite+pysqlite:///:memory:"
    )
    engine = make_engine(settings)
    Base.metadata.create_all(engine)
    sessions = session_factory(engine)
    with sessions.begin() as session:
        seed(session, AS_OF)
    yield sessions, BusinessService(sessions, today=lambda: AS_OF)
    engine.dispose()
