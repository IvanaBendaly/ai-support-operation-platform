import os
import subprocess
import sys
from datetime import date

from alembic import command
from alembic.config import Config
from sqlalchemy import select

from northstar.config import Settings
from northstar.db import make_engine, session_factory
from northstar.domain import BusinessService
from northstar.seed import BUSINESS_RECORDS


def test_seed_reset_cli_is_reproducible(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", url)
    monkeypatch.setenv("NORTHSTAR_ENVIRONMENT", "test")
    command.upgrade(Config("alembic.ini"), "head")
    engine = make_engine(Settings(_env_file=None, environment="test", database_url=url))
    sessions = session_factory(engine)
    args = [sys.executable, "-m", "northstar.seed", "--as-of", "2026-10-12"]

    def snapshot():
        with sessions() as session:
            return {
                model.__tablename__: session.execute(select(model.__table__).order_by(model.id))
                .mappings()
                .all()
                for model in BUSINESS_RECORDS
            }

    try:
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=15)
        assert result.returncode == 0, result.stderr
        before = snapshot()
        result = subprocess.run(args, check=False, capture_output=True, text=True, timeout=15)
        assert result.returncode != 0 and "empty business database" in result.stderr
        assert snapshot() == before
        BusinessService(sessions, today=lambda: date(2026, 10, 12)).refund(
            "alice", "alice-active", "inv-eligible", "cli-mutation"
        )
        result = subprocess.run(
            [*args, "--reset"], check=False, capture_output=True, text=True, timeout=15
        )
        assert result.returncode == 0, result.stderr
        assert snapshot() == before
        environment = dict(
            os.environ,
            NORTHSTAR_ENVIRONMENT="production",
            NORTHSTAR_DATABASE_URL="postgresql+psycopg://db/unused",
            NORTHSTAR_ALLOWED_ORIGINS='["https://support.example.test"]',
        )
        result = subprocess.run(
            [*args, "--reset"],
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        assert result.returncode != 0 and "disabled in production" in result.stderr
    finally:
        engine.dispose()
