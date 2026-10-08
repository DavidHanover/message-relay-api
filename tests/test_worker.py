from datetime import timedelta

from sqlalchemy import update

from app.models import Message, MessageStatus
from app.providers.registry import ProviderRegistry
from app.worker import process_batch
from tests.conftest import email_payload, sms_payload


def _send(client, payload) -> str:
    return client.post("/v1/messages", json=payload).json()["id"]


def _make_due(db):
    """Skip the backoff wait so the next batch picks up retries immediately."""
    db.execute(update(Message).values(next_attempt_at=Message.created_at))
    db.commit()


def _detail(client, message_id):
    return client.get(f"/v1/messages/{message_id}").json()


def test_email_and_sms_are_sent(client, db, settings):
    email_id = _send(client, email_payload())
    sms_id = _send(client, sms_payload())

    assert process_batch(db, ProviderRegistry(settings), settings) == 2

    email = _detail(client, email_id)
    assert email["status"] == "sent"
    assert email["provider"] == "sendgrid"
    assert email["provider_message_id"].startswith("sg_")
    assert email["attempts"] == 1
    assert [e["event_type"] for e in email["events"]] == ["queued", "sent"]

    sms = _detail(client, sms_id)
    assert sms["status"] == "sent"
    assert sms["provider"] == "twilio"
    assert sms["provider_message_id"].startswith("SM")


def test_mailgun_provider(client, db, settings):
    settings = settings.model_copy(update={"email_provider": "mailgun"})
    msg_id = _send(client, email_payload())
    process_batch(db, ProviderRegistry(settings), settings)
    msg = _detail(client, msg_id)
    assert msg["status"] == "sent"
    assert msg["provider"] == "mailgun"


def test_transient_failure_retries_then_fails(client, db, settings):
    settings = settings.model_copy(update={"max_attempts": 3})
    registry = ProviderRegistry(settings)
    msg_id = _send(client, email_payload(to="transient-fail@example.com"))
    db.execute(update(Message).values(max_attempts=3))
    db.commit()

    process_batch(db, registry, settings)
    msg = _detail(client, msg_id)
    assert msg["status"] == "queued"
    assert msg["attempts"] == 1
    assert msg["next_attempt_at"] > msg["created_at"]

    # Not due yet, so nothing is claimed.
    assert process_batch(db, registry, settings) == 0

    for _ in range(2):
        _make_due(db)
        process_batch(db, registry, settings)

    msg = _detail(client, msg_id)
    assert msg["status"] == "failed"
    assert msg["attempts"] == 3
    assert "503" in msg["last_error"]
    assert [e["event_type"] for e in msg["events"]] == [
        "queued", "retry_scheduled", "retry_scheduled", "failed",
    ]
    assert msg["events"][-1]["detail"]["reason"] == "max_attempts_exhausted"


def test_permanent_failure_is_not_retried(client, db, settings):
    msg_id = _send(client, sms_payload(to="+15005550002"))
    process_batch(db, ProviderRegistry(settings), settings)
    msg = _detail(client, msg_id)
    assert msg["status"] == "failed"
    assert msg["attempts"] == 1
    assert msg["events"][-1]["detail"]["reason"] == "permanent"


def test_stale_sending_messages_are_reaped(client, db, settings):
    msg_id = _send(client, email_payload())
    # Simulate a worker that crashed mid-send 10 minutes ago.
    db.execute(
        update(Message).values(
            status=MessageStatus.sending, locked_at=Message.created_at - timedelta(minutes=10)
        )
    )
    db.commit()

    process_batch(db, ProviderRegistry(settings), settings)
    assert _detail(client, msg_id)["status"] == "sent"
