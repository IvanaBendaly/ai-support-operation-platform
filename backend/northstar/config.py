from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NORTHSTAR_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    admin_token: SecretStr | None = Field(default=None, min_length=32)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    model_provider: Literal["disabled", "openai"] = "disabled"
    model_name: str | None = Field(default=None, min_length=1, max_length=100)
    provider_api_key: SecretStr | None = None
    model_timeout_seconds: float = Field(default=30, gt=0, le=120, allow_inf_nan=False)
    model_max_output_tokens: int = Field(default=1024, ge=1, le=16384)

    @field_validator("admin_token", mode="before")
    @classmethod
    def optional_admin_token(cls, value):
        return None if value == "" else value

    @field_validator("database_url")
    @classmethod
    def database_scheme(cls, value: SecretStr) -> SecretStr:
        try:
            url = make_url(value.get_secret_value())
        except Exception:
            raise ValueError("database_url must be a valid SQLAlchemy URL") from None
        if url.drivername not in {"postgresql+psycopg", "sqlite+pysqlite"}:
            raise ValueError("use postgresql+psycopg (or sqlite+pysqlite in tests)")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def origins(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("allowed_origins must contain explicit HTTP(S) origins")
        for origin in value:
            try:
                parsed = urlsplit(origin)
                valid = (
                    parsed.scheme in {"http", "https"}
                    and parsed.hostname
                    and not parsed.username
                    and not parsed.password
                    and not parsed.path
                    and not parsed.query
                    and not parsed.fragment
                    and not any(c.isspace() for c in origin)
                    and "*" not in origin
                )
                _ = parsed.port
            except ValueError:
                valid = False
            if not valid:
                raise ValueError(
                    "allowed_origins must contain explicit HTTP(S) origins without paths"
                )
        return value

    @model_validator(mode="after")
    def runtime_database(self):
        if self.environment != "test" and self.database_url.get_secret_value().startswith("sqlite"):
            raise ValueError("SQLite is only supported in the test environment")
        if self.environment == "production" and any(
            not origin.startswith("https://") for origin in self.allowed_origins
        ):
            raise ValueError("production origins must use HTTPS")
        if self.model_provider != "disabled":
            if not self.model_name or not self.model_name.strip():
                raise ValueError("model_name is required when a model provider is configured")
            if not self.provider_api_key or not self.provider_api_key.get_secret_value().strip():
                raise ValueError("provider_api_key is required when a model provider is configured")
        return self


def load_settings() -> Settings:
    """Provide actionable startup errors without environment values or chained exceptions."""
    try:
        return Settings()
    except ValidationError as error:
        issues = [
            f"{'.'.join(map(str, item['loc'])) or 'configuration'}: {item['msg']}"
            for item in error.errors()
        ]
        raise RuntimeError("Invalid Northstar configuration: " + "; ".join(issues)) from None
    except SettingsError:
        raise RuntimeError("Invalid Northstar environment encoding; check JSON settings.") from None
