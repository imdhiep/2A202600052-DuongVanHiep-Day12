"""Centralized 12-factor configuration for the final lab project."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env.local", override=True)


def _env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _env_float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _env_list(name: str, default: str) -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: _env_int("PORT", 8000))
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development").lower())
    debug: bool = field(default_factory=lambda: _env_bool("DEBUG", False))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO").upper())
    web_concurrency: int = field(default_factory=lambda: _env_int("WEB_CONCURRENCY", 2))

    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "Production AI Agent"))
    app_version: str = field(default_factory=lambda: os.getenv("APP_VERSION", "1.0.0"))

    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))

    agent_api_key: str = field(default_factory=lambda: os.getenv("AGENT_API_KEY", "dev-key-change-me"))
    jwt_secret: str = field(default_factory=lambda: os.getenv("JWT_SECRET", "dev-jwt-secret"))
    jwt_algorithm: str = field(default_factory=lambda: os.getenv("JWT_ALGORITHM", "HS256"))
    access_token_expire_minutes: int = field(
        default_factory=lambda: _env_int("ACCESS_TOKEN_EXPIRE_MINUTES", 60)
    )
    enable_demo_jwt_login: bool = field(
        default_factory=lambda: _env_bool("ENABLE_DEMO_JWT_LOGIN", True)
    )
    demo_admin_username: str = field(default_factory=lambda: os.getenv("DEMO_ADMIN_USERNAME", "student"))
    demo_admin_password: str = field(default_factory=lambda: os.getenv("DEMO_ADMIN_PASSWORD", "demo123"))
    allowed_origins: list[str] = field(default_factory=lambda: _env_list("ALLOWED_ORIGINS", "*"))

    rate_limit_per_minute: int = field(default_factory=lambda: _env_int("RATE_LIMIT_PER_MINUTE", 10))
    rate_limit_window_seconds: int = field(
        default_factory=lambda: _env_int("RATE_LIMIT_WINDOW_SECONDS", 60)
    )

    monthly_budget_usd: float = field(default_factory=lambda: _env_float("MONTHLY_BUDGET_USD", 10.0))
    global_monthly_budget_usd: float = field(
        default_factory=lambda: _env_float("GLOBAL_MONTHLY_BUDGET_USD", 100.0)
    )

    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    require_redis_in_production: bool = field(
        default_factory=lambda: _env_bool("REQUIRE_REDIS_IN_PRODUCTION", True)
    )
    session_ttl_seconds: int = field(default_factory=lambda: _env_int("SESSION_TTL_SECONDS", 86400))
    history_turn_limit: int = field(default_factory=lambda: _env_int("HISTORY_TURN_LIMIT", 10))

    def validate(self) -> "Settings":
        logger = logging.getLogger(__name__)

        if self.port <= 0:
            raise ValueError("PORT must be a positive integer.")
        if self.rate_limit_per_minute <= 0:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be positive.")
        if self.monthly_budget_usd <= 0:
            raise ValueError("MONTHLY_BUDGET_USD must be positive.")
        if self.history_turn_limit <= 0:
            raise ValueError("HISTORY_TURN_LIMIT must be positive.")

        if self.environment == "production":
            if self.agent_api_key == "dev-key-change-me":
                raise ValueError("AGENT_API_KEY must be set in production.")
            if self.jwt_secret == "dev-jwt-secret":
                raise ValueError("JWT_SECRET must be set in production.")
            if self.require_redis_in_production and not self.redis_url:
                raise ValueError("REDIS_URL must be configured in production.")

        if not self.openai_api_key:
            logger.warning("OPENAI_API_KEY not set; using mock LLM responses.")

        return self


settings = Settings().validate()
