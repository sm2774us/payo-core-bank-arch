"""Centralized, environment-driven configuration.

Kept as a single Pydantic settings object so every config value is typed,
validated at process start, and visible in one place for an auditor/reviewer.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///./local.db"
    kafka_bootstrap_servers: str = "localhost:9092"
    outbox_topic: str = "payo.ledger.transactions.v1"
    service_name: str = "ledger-core"
    environment: str = "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
