"""Dispatch worker: claims queued messages from Postgres and sends them via the configured vendor.

Run with `python -m app.worker`. Safe to run many replicas; FOR UPDATE SKIP LOCKED
ensures each message is claimed by exactly one worker at a time.
"""

import logging
import random
import signal
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db import SessionLocal, init_db
from app.models import Message, MessageEvent, MessageStatus
from app.providers.base import PermanentError, TransientError
from app.providers.registry import ProviderRegistry

log = logging.getLogger("worker")


def claim_batch(db: Session, batch_size: int) -> list[Message]:
    due = (
        select(Message.id)
        .where(Message.status == MessageStatus.queued, Message.next_attempt_at <= func.now())
        .order_by(Message.created_at)
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    claimed = db.scalars(
        update(Message)
        .where(Message.id.in_(due.scalar_subquery()))
        .values(status=MessageStatus.sending, locked_at=func.now(), attempts=Message.attempts + 1)
        .returning(Message),
        execution_options={"synchronize_session": False},
    ).all()
    db.commit()
    return list(claimed)


def reap_stale(db: Session, stale_after_seconds: int) -> int:
    """Requeue messages stuck in 'sending' (worker crashed mid-send). Gives at-least-once delivery."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_seconds)
    result = db.execute(
        update(Message)
        .where(Message.status == MessageStatus.sending, Message.locked_at < cutoff)
        .values(status=MessageStatus.queued, locked_at=None)
    )
    db.commit()
    if result.rowcount:
        log.warning("requeued %d stale messages", result.rowcount)
    return result.rowcount


def backoff_seconds(attempt: int, base: float) -> float:
    return base * 2 ** (attempt - 1) + random.uniform(0, base)


def deliver(db: Session, msg: Message, registry: ProviderRegistry, settings: Settings) -> None:
    provider = registry.get(msg.channel)
    msg.provider = provider.name
    msg.locked_at = None
    try:
        result = provider.send(msg)
    except TransientError as e:
        msg.last_error = str(e)
        if msg.attempts < msg.max_attempts:
            delay = backoff_seconds(msg.attempts, settings.retry_base_seconds)
            msg.status = MessageStatus.queued
            msg.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
            event = MessageEvent(
                event_type="retry_scheduled",
                detail={"attempt": msg.attempts, "error": str(e), "retry_in_seconds": round(delay, 2)},
            )
        else:
            msg.status = MessageStatus.failed
            event = MessageEvent(
                event_type="failed",
                detail={"attempt": msg.attempts, "error": str(e), "reason": "max_attempts_exhausted"},
            )
    except PermanentError as e:
        msg.last_error = str(e)
        msg.status = MessageStatus.failed
        event = MessageEvent(
            event_type="failed", detail={"attempt": msg.attempts, "error": str(e), "reason": "permanent"}
        )
    else:
        msg.status = MessageStatus.sent
        msg.provider_message_id = result.provider_message_id
        msg.last_error = None
        event = MessageEvent(
            event_type="sent",
            detail={"attempt": msg.attempts, "provider": result.provider, "provider_message_id": result.provider_message_id},
        )

    event.message_id = msg.id
    db.add(event)
    db.commit()
    log.info("message %s -> %s (attempt %d/%d)", msg.id, msg.status.value, msg.attempts, msg.max_attempts)


def process_batch(db: Session, registry: ProviderRegistry, settings: Settings) -> int:
    reap_stale(db, settings.stale_lock_seconds)
    messages = claim_batch(db, settings.worker_batch_size)
    for msg in messages:
        try:
            deliver(db, msg, registry, settings)
        except Exception:
            # Unexpected bug: leave it in 'sending' so the reaper retries it later.
            log.exception("unexpected error delivering %s", msg.id)
            db.rollback()
    return len(messages)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    init_db()
    registry = ProviderRegistry(settings)

    running = True

    def stop(*_):
        nonlocal running
        log.info("shutdown requested; finishing current batch")
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    log.info("worker started (email=%s, sms=%s, mock=%s)", settings.email_provider, settings.sms_provider, settings.mock_vendors)
    while running:
        try:
            with SessionLocal() as db:
                processed = process_batch(db, registry, settings)
        except Exception:
            log.exception("worker loop error")
            processed = 0
        if not processed:
            time.sleep(settings.worker_poll_interval)


if __name__ == "__main__":
    main()
