import os

# Point at the dedicated test database before any app module builds the engine.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://messaging:messaging@127.0.0.1:5433/messaging_test"
)
os.environ["MOCK_VENDORS"] = "true"
os.environ["MOCK_FAILURE_RATE"] = "0"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _schema():
    init_db()


@pytest.fixture(autouse=True)
def _clean_tables():
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE message_events, messages CASCADE"))


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def settings():
    return get_settings()


def email_payload(**overrides):
    return {
        "channel": "email",
        "recipient_type": "member",
        "requested_by": "care-team",
        "to": "jane@example.com",
        "subject": "Your appointment",
        "body_text": "See you tomorrow at 10am.",
        **overrides,
    }


def sms_payload(**overrides):
    return {
        "channel": "sms",
        "recipient_type": "provider",
        "requested_by": "scheduling",
        "to": "+15551234567",
        "body_text": "Reminder: shift starts at 9am.",
        **overrides,
    }
