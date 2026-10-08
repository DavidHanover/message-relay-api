from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://messaging:messaging@127.0.0.1:5433/messaging"

    # Company-owned sender identity. Callers cannot override these.
    default_from_email: str = "notifications@company.com"
    default_from_name: str = "Company Notifications"
    default_sms_from: str = "+15550000000"

    # One configured vendor per channel.
    email_provider: Literal["sendgrid", "mailgun"] = "sendgrid"
    sms_provider: Literal["twilio"] = "twilio"

    # Mock vendor behaviour. When true, adapters route through httpx.MockTransport.
    mock_vendors: bool = True
    mock_failure_rate: float = 0.0

    # Fake vendor credentials (never real; only used to build realistic requests).
    sendgrid_api_key: str = "SG.mock"
    mailgun_api_key: str = "mock-key"
    mailgun_domain: str = "mg.company.com"
    twilio_account_sid: str = "ACmock"
    twilio_auth_token: str = "mock-token"

    # Worker tuning.
    max_attempts: int = 5
    retry_base_seconds: float = 2.0
    worker_batch_size: int = 10
    worker_poll_interval: float = 1.0
    stale_lock_seconds: int = 300


@lru_cache
def get_settings() -> Settings:
    return Settings()
