from __future__ import annotations

from dataclasses import dataclass
import os

from dotenv import load_dotenv


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_int(name: str, default: int) -> int:
    value = _env(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    value = _env(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    telegram_timeout: int
    openai_api_key: str
    openai_model: str
    openai_temperature: float
    openai_max_tokens: int
    openai_timeout: int
    openai_base_url: str
    db_path: str
    polling_timeout: int
    polling_sleep: float
    offset_file: str | None
    log_level: str


def load_settings() -> Settings:
    load_dotenv()

    telegram_token = _env("TELEGRAM_BOT_TOKEN", "")
    openai_api_key = _env("OPENAI_API_KEY", "")

    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY is required")

    return Settings(
        telegram_token=telegram_token,
        telegram_timeout=_env_int("TELEGRAM_TIMEOUT", 20),
        openai_api_key=openai_api_key,
        openai_model=_env("OPENAI_MODEL", "gpt-3.5-turbo"),
        openai_temperature=_env_float("OPENAI_TEMPERATURE", 0.7),
        openai_max_tokens=_env_int("OPENAI_MAX_TOKENS", 1200),
        openai_timeout=_env_int("OPENAI_TIMEOUT", 30),
        openai_base_url=_env("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        db_path=_env("DATABASE_PATH", os.path.join("data", "taro.db")),
        polling_timeout=_env_int("POLLING_TIMEOUT", 30),
        polling_sleep=_env_float("POLLING_SLEEP", 1.0),
        offset_file=_env("BOT_OFFSET_FILE"),
        log_level=_env("LOG_LEVEL", "INFO"),
    )
