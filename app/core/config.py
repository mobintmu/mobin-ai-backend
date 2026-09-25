from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "test", "production"] = "local"
    database_url: str = "postgresql+asyncpg://mobin:mobin@localhost:5432/mobin"
    token_hash_key: str = "local-only-change-this-key-before-production"
    contact_encryption_key: str = ""
    ai_base_url: str = "http://localhost:8001/v1"
    ai_api_key: str = "local-fake-key"
    ai_model: str = "fake-model"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    turnstile_secret: str = "local-test-secret"
    turnstile_hostname: str = "chat.mobinshaterian.com"
    turnstile_action: str = "client_register"
    public_api_url: str = "http://localhost:8000"
    cors_origins: str = "https://chat.mobinshaterian.com,http://localhost:5173"
    trusted_proxies: str = "127.0.0.1/32"
    token_ttl_days: int = 30
    registration_grant_ttl_minutes: int = 5
    monthly_request_budget: int = 10000
    monthly_model_budget_usd: float = 0.0
    max_request_cost_usd: float = 0.0
    ai_input_usd_per_million: float = 0.0
    ai_output_usd_per_million: float = 0.0
    token_rate_limit_per_minute: int = 5
    ip_rate_limit_per_hour: int = 30
    retention_days: int = 365
    knowledge_root: Path = Path("knowledge/releases")
    question_max_chars: int = 4000
    ai_timeout_seconds: float = 45
    ai_max_tokens: int = 800
    ai_concurrency: int = 4

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use PostgreSQL and asyncpg")
        return value

    @model_validator(mode="after")
    def require_production_secrets(self) -> "Settings":
        if self.contact_encryption_key:
            try:
                Fernet(self.contact_encryption_key.encode())
            except (ValueError, TypeError) as exc:
                raise ValueError("CONTACT_ENCRYPTION_KEY must be a Fernet key") from exc
        if self.app_env == "production":
            values = (
                self.token_hash_key,
                self.contact_encryption_key,
                self.ai_api_key,
                self.ai_model,
                self.embedding_api_key,
                self.embedding_model,
                self.turnstile_secret,
            )
            if any(
                not value or "replace" in value.lower() or value.startswith("local-")
                for value in values
            ):
                raise ValueError("Production secrets and models must be configured")
            if len(self.token_hash_key) < 32:
                raise ValueError("TOKEN_HASH_KEY must contain at least 32 characters")
            if (
                not self.embedding_base_url
                or not self.ai_base_url.startswith("https://")
                or not self.embedding_base_url.startswith("https://")
            ):
                raise ValueError("Production provider URLs must use HTTPS")
            if not self.public_api_url.startswith("https://"):
                raise ValueError("PUBLIC_API_URL must use HTTPS")
            if (
                min(
                    self.monthly_model_budget_usd,
                    self.max_request_cost_usd,
                    self.ai_input_usd_per_million,
                    self.ai_output_usd_per_million,
                )
                <= 0
            ):
                raise ValueError("Production model budget and token prices must be positive")
            if "https://chat.mobinshaterian.com" not in self.origins or "*" in self.origins:
                raise ValueError("Production CORS must permit the exact chat origin")
            if not self.trusted_proxies or self.trusted_proxies == "127.0.0.1/32":
                raise ValueError("Production trusted proxy addresses are required")
        if (
            min(
                self.token_ttl_days,
                self.registration_grant_ttl_minutes,
                self.monthly_request_budget,
                self.token_rate_limit_per_minute,
                self.ip_rate_limit_per_hour,
                self.retention_days,
                self.ai_max_tokens,
                self.ai_concurrency,
            )
            <= 0
        ):
            raise ValueError("Limits and validity periods must be positive")
        return self

    @property
    def origins(self) -> list[str]:
        return [part.strip() for part in self.cors_origins.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
