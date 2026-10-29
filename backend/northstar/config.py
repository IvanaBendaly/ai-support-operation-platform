from typing import Literal
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.exceptions import SettingsError
from sqlalchemy.engine import make_url


class ExtractionSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    liteparse_enabled: bool = True
    minimum_characters: int = Field(default=80, ge=1, le=10000)
    # No universal confidence cutoff: configure only after evaluation on permitted examples.
    confidence_floor: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    field_schema: dict | None = None
    field_confidence_floor: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    llamaextract_api_key: SecretStr | None = None
    llamaextract_project_id: str | None = None
    external_public_allowed: bool = False
    external_internal_allowed: bool = False
    external_confidential_exception: bool = False


class RetrievalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    result_limit: int = Field(default=5, ge=1, le=20)
    context_chars: int = Field(default=8000, ge=256, le=32000)
    section_chars: int = Field(default=2000, ge=128, le=2000)
    query_chars: int = Field(default=2000, ge=1, le=8000)
    candidate_limit: int = Field(default=20, ge=1, le=100)
    min_score: float = Field(default=0.22, ge=0, le=1, allow_inf_nan=False)
    ambiguity_margin: float = Field(default=0.06, ge=0, le=1, allow_inf_nan=False)
    dimensions: int = Field(default=32, ge=1, le=64)
    max_sections: int = Field(default=256, ge=1, le=512)
    max_vocabulary: int = Field(default=4096, ge=32, le=8192)

    @model_validator(mode="after")
    def candidate_count(self):
        if self.candidate_limit < self.result_limit:
            raise ValueError("candidate_limit must be at least result_limit")
        return self


class StorageSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    backend: Literal["s3", "filesystem"] = "s3"
    endpoint: str | None = None
    bucket: str = "northstar-originals"
    region: str = "us-east-1"
    access_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    directory: str = ".test-objects"
    encryption: Literal["AES256", "aws:kms"] | None = None
    kms_key_id: str | None = None
    # Operator attestation; application code cannot verify infrastructure accreditation.
    restricted_environment_approved: bool = False


class ReviewSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: Literal["disabled", "auto", "openai", "ollama"] = "disabled"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: SecretStr | None = None
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:4b"
    local_environment_approved: bool = False
    restricted_local_approved: bool = False
    external_public_allowed: bool = False
    external_internal_allowed: bool = False
    external_confidential_exception: bool = False
    timeout_seconds: float = Field(default=60, gt=0, le=120)
    max_input_chars: int = Field(default=12000, ge=2000, le=24000)
    max_output_tokens: int = Field(default=1500, ge=256, le=4096)

    @field_validator("ollama_url")
    @classmethod
    def private_endpoint(cls, value):
        import ipaddress

        parsed = urlsplit(value)
        host = parsed.hostname or ""
        private = host in {"localhost", "ollama", "host.docker.internal"}
        try:
            address = ipaddress.ip_address(host)
            private = address.is_private and not address.is_unspecified
        except ValueError:
            pass
        if (
            not private
            or parsed.scheme not in {"http", "https"}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError(
                "ollama_url must name a private IP, localhost, or the Ollama Docker host"
            )
        return value.rstrip("/")

    @field_validator("ollama_model")
    @classmethod
    def local_model(cls, value):
        if "cloud" in value.lower() or "/" in value or not value.strip():
            raise ValueError("Use a locally installed model tag, never a cloud model")
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NORTHSTAR_",
        env_nested_delimiter="__",
        env_file=".env",
        extra="ignore",
        hide_input_in_errors=True,
    )
    retrieval: RetrievalSettings = Field(default_factory=RetrievalSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    review: ReviewSettings = Field(default_factory=ReviewSettings)
    extraction: ExtractionSettings = Field(default_factory=ExtractionSettings)
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
        if self.storage.backend == "filesystem" and self.environment != "test":
            raise ValueError("Filesystem object storage is only supported in tests")
        if (
            self.environment == "production"
            and self.storage.endpoint
            and not self.storage.endpoint.startswith("https://")
        ):
            raise ValueError("Production object storage must use HTTPS")
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
