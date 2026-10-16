import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from northstar.config import Settings, load_settings


@pytest.mark.parametrize(
    "origin",
    [
        "https://",
        "https://example.com/path",
        "https://user:password@example.com",
        "https://*.example.com",
        "https://example.com:invalid",
        "https://exa mple.com",
        "https://example.com?x=1",
        "https://example.com#fragment",
    ],
)
def test_invalid_origins_rejected(origin):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None, database_url="postgresql+psycopg://db/name", allowed_origins=[origin]
        )


def test_model_configuration_is_disabled_by_default_and_secrets_are_private():
    base = {"_env_file": None, "database_url": "postgresql+psycopg://db/name"}
    assert Settings(**base).model_provider == "disabled"
    with pytest.raises(ValidationError, match="model_name"):
        Settings(**base, model_provider="openai")
    with pytest.raises(ValidationError, match="provider_api_key"):
        Settings(**base, model_provider="openai", model_name="configured-model")
    configured = Settings(
        **base,
        model_provider="openai",
        model_name="configured-model",
        provider_api_key="private-test-credential",
    )
    assert "private-test-credential" not in repr(configured)
    assert "private-test-credential" not in configured.model_dump_json()
    with pytest.raises(ValidationError):
        Settings(**base, model_timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(**base, model_max_output_tokens=0)


@pytest.mark.parametrize("environment", ["development", "test", "production"])
def test_typed_environment_profiles(environment):
    settings = Settings(
        _env_file=None,
        environment=environment,
        database_url="postgresql+psycopg://db/name",
        allowed_origins=["https://support.example.test"],
    )
    assert settings.environment == environment


def test_malformed_json_configuration_fails_without_value(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("NORTHSTAR_ALLOWED_ORIGINS", "private-bad-input")
    with pytest.raises(RuntimeError, match="environment encoding") as error:
        load_settings()
    assert "private-bad-input" not in str(error.value)


def test_documented_startup_fails_clearly_without_configuration(tmp_path):
    environment = {
        key: value for key, value in os.environ.items() if not key.startswith("NORTHSTAR_")
    }
    # Use the real documented Uvicorn entry point, outside a directory containing .env.
    result = subprocess.run(
        [sys.executable, "-m", "uvicorn", "northstar.api:create_app", "--factory"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert "Invalid Northstar configuration: database_url" in result.stderr


def test_failed_migration_does_not_report_success(tmp_path):
    environment = dict(
        os.environ,
        NORTHSTAR_ENVIRONMENT="test",
        NORTHSTAR_DATABASE_URL=f"sqlite+pysqlite:///{tmp_path / 'missing' / 'db.sqlite'}",
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(Path("alembic.ini").resolve()),
            "upgrade",
            "head",
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode != 0
    assert not (tmp_path / "missing" / "db.sqlite").exists()
