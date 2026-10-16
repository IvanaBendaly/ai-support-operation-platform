import json
import logging
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from northstar.api import create_app, expected_revision
from northstar.config import Settings
from northstar.db import make_engine
from northstar.logging import JsonFormatter


def configuration(url="sqlite+pysqlite:///:memory:"):
    return Settings(_env_file=None, environment="test", database_url=url)


def migrate(monkeypatch, url, revision="head"):
    monkeypatch.setenv("NORTHSTAR_ENVIRONMENT", "test")
    monkeypatch.setenv("NORTHSTAR_DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), revision)


def test_missing_and_invalid_configuration(monkeypatch):
    monkeypatch.delenv("NORTHSTAR_DATABASE_URL", raising=False)
    with pytest.raises(ValidationError, match="database_url"):
        Settings(_env_file=None)
    with pytest.raises(ValidationError) as error:
        configuration("mysql://name:SECRET_PASSWORD@db/name")
    assert "SECRET_PASSWORD" not in str(error.value)
    with pytest.raises(ValidationError, match="only supported in the test"):
        Settings(_env_file=None, database_url="sqlite+pysqlite:///:memory:")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_url="postgresql+psycopg://db/name", allowed_origins=["*"])
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(_env_file=None, environment="production", database_url="postgresql+psycopg://db/a")


def test_liveness_does_not_require_a_database_and_missing_schema_is_not_ready():
    engine = make_engine(configuration())
    with TestClient(create_app(configuration(), engine)) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"
        assert response.headers["x-request-id"]
        response = client.get("/api/ready")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "database_not_ready"
    engine.dispose()


def test_migration_empty_database_readiness_and_downgrade(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"
    migrate(monkeypatch, url)
    engine = make_engine(configuration(url))
    with TestClient(create_app(configuration(url), engine)) as client:
        assert client.get("/api/ready").json()["schema"] == expected_revision()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO alembic_version VALUES ('unexpected-branch')"))
        assert client.get("/api/ready").status_code == 503
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM alembic_version WHERE version_num='unexpected-branch'")
            )
        with engine.begin() as connection:
            connection.execute(text("UPDATE alembic_version SET version_num = 'old'"))
        assert client.get("/api/ready").json()["error"]["code"] == "schema_not_ready"
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE alembic_version SET version_num = :v"), {"v": expected_revision()}
            )
    command.downgrade(Config("alembic.ini"), "base")
    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM alembic_version")).scalar() == 0
    command.upgrade(Config("alembic.ini"), "head")
    engine.dispose()


def test_unavailable_database_does_not_disclose_connection_details():
    engine = make_engine(configuration())
    with TestClient(create_app(configuration(), engine)) as client:
        with patch.object(
            engine, "connect", side_effect=OperationalError("password=secret", {}, None)
        ):
            response = client.get("/api/ready")
        assert response.status_code == 503
        assert "secret" not in response.text
    engine.dispose()


def test_errors_validation_and_cors():
    engine = make_engine(configuration())
    app = create_app(configuration(), engine)

    class Payload(BaseModel):
        count: int

    @app.post("/test-validation")
    def validate(payload: Payload):
        return payload

    @app.get("/test-internal")
    def fail():
        raise RuntimeError("secret token")

    with TestClient(app) as client:
        response = client.post("/test-validation", json={"count": "PRIVATE_INPUT"})
        assert response.status_code == 422
        assert "PRIVATE_INPUT" not in response.text
        assert response.json()["error"]["details"][0]["field"] == "body.count"
        response = client.get("/test-internal")
        assert response.status_code == 500
        assert "secret" not in response.text
        assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
        assert client.get("/not-found").json()["error"]["code"] == "http_error"
        response = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        response = client.get("/api/health", headers={"Origin": "https://untrusted.example"})
        assert "access-control-allow-origin" not in response.headers
    engine.dispose()


def test_log_formatter_whitelists_context():
    record = logging.makeLogRecord(
        {
            "msg": "request_completed",
            "levelname": "INFO",
            "request_id": "test-id",
            "authorization": "secret",
        }
    )
    result = JsonFormatter().format(record)
    assert "secret" not in result
    assert json.loads(result)["request_id"] == "test-id"


@pytest.mark.postgres
def test_postgres_empty_database_migrations(postgres_engine):
    settings = configuration(str(postgres_engine.url))
    with TestClient(create_app(settings, postgres_engine)) as client:
        assert client.get("/api/ready").status_code == 200
    command.downgrade(Config("alembic.ini"), "base")
    command.upgrade(Config("alembic.ini"), "head")
