from datetime import date, datetime

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, inspect, select, text
from sqlalchemy.exc import IntegrityError

from northstar.config import Settings
from northstar.db import make_engine


@pytest.mark.parametrize("invalid_legacy_state", [False, True])
def test_existing_business_data_survives_metadata_upgrade(
    tmp_path, monkeypatch, invalid_legacy_state
):
    url = f"sqlite+pysqlite:///{tmp_path / 'legacy.db'}"
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", url)
    monkeypatch.setenv("NORTHSTAR_ENVIRONMENT", "test")
    config = Config("alembic.ini")
    command.upgrade(config, "0002")
    engine = make_engine(Settings(_env_file=None, environment="test", database_url=url))
    metadata = MetaData()
    metadata.reflect(engine)
    records = {
        "customers": {"id": "legacy", "name": "Legacy Demo", "email": "legacy@example.test"},
        "accounts": {
            "id": "account",
            "customer_id": "legacy",
            "name": "Account",
            "status": "ACTIVE",
        },
        "plans": {
            "id": "starter",
            "name": "Starter",
            "price_minor": 1900,
            "currency": "USD",
            "enabled": True,
        },
        "subscriptions": {
            "id": "sub",
            "account_id": "account",
            "plan_id": "starter",
            "status": "ACTIVE",
            "started_on": date(2026, 1, 1),
            "version": 1,
        },
        "invoices": {
            "id": "invoice",
            "account_id": "account",
            "amount_minor": 1900,
            "refunded_minor": 1900,
            "currency": "USD",
            "status": "PAID",
            "issued_on": date(2026, 1, 2),
        },
        "refunds": {
            "id": "refund",
            "invoice_id": "invoice",
            "amount_minor": 1900,
            "created_at": datetime(2026, 1, 3),
        },
    }
    with engine.begin() as connection:
        for name, record in records.items():
            connection.execute(metadata.tables[name].insert(), record)
        if invalid_legacy_state:
            connection.execute(text("UPDATE invoices SET status='UNPAID'"))
    if invalid_legacy_state:
        with pytest.raises(IntegrityError):
            command.upgrade(config, "head")
        assert "created_at" not in {
            column["name"] for column in inspect(engine).get_columns("customers")
        }
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
                == "0002"
            )
            assert connection.execute(text("SELECT refunded_minor FROM invoices")).scalar() == 1900
        engine.dispose()
        return
    command.upgrade(config, "head")
    updated = MetaData()
    updated.reflect(engine)
    with engine.connect() as connection:
        refund = connection.execute(select(updated.tables["refunds"])).mappings().one()
        assert refund["reason"] == "legacy_refund"
        assert refund["state"] == "COMPLETED"
        for name, record in records.items():
            stored = connection.execute(select(updated.tables[name])).mappings().one()
            assert all(stored[key] == value for key, value in record.items())
    command.check(config)
    command.downgrade(config, "0002")
    with engine.connect() as connection:
        assert (
            connection.execute(select(metadata.tables["refunds"])).mappings().one()["amount_minor"]
            == 1900
        )
    engine.dispose()
