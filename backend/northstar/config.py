from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NORTHSTAR_", env_file=".env", extra="ignore", hide_input_in_errors=True
    )
    environment: Literal["development", "test", "production"] = "development"
    database_url: SecretStr
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

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
        if not value or any(not v.startswith(("http://", "https://")) for v in value):
            raise ValueError("allowed_origins must contain explicit HTTP(S) origins")
        return value

    @model_validator(mode="after")
    def runtime_database(self):
        if self.environment != "test" and self.database_url.get_secret_value().startswith("sqlite"):
            raise ValueError("SQLite is only supported in the test environment")
        if self.environment == "production" and any(
            not origin.startswith("https://") for origin in self.allowed_origins
        ):
            raise ValueError("production origins must use HTTPS")
        return self
