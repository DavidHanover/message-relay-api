import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Channel, Message, MessageEvent
from app.schemas import EmailSendRequest, SmsSendRequest


class IdempotencyConflict(Exception):
    """Same Idempotency-Key reused with a different request body."""


def request_hash(req: EmailSendRequest | SmsSendRequest) -> str:
    payload = json.dumps(req.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _find_existing(db: Session, requested_by: str, key: str) -> Message | None:
    return db.scalar(
        select(Message).where(Message.requested_by == requested_by, Message.idempotency_key == key)
    )


def _check_replay(existing: Message, digest: str) -> Message:
    if existing.request_hash != digest:
        raise IdempotencyConflict
    return existing


def create_message(
    db: Session,
    req: EmailSendRequest | SmsSendRequest,
    settings: Settings,
    idempotency_key: str | None = None,
) -> tuple[Message, bool]:
    """Queue a message. Returns (message, created); created is False on an idempotent replay."""
    digest = request_hash(req)

    if idempotency_key:
        existing = _find_existing(db, req.requested_by, idempotency_key)
        if existing:
            return _check_replay(existing, digest), False

    is_email = req.channel == Channel.email.value
    msg = Message(
        channel=Channel(req.channel),
        recipient_type=req.recipient_type,
        to_address=str(req.to),
        from_address=settings.default_from_email if is_email else settings.default_sms_from,
        subject=req.subject if is_email else None,
        body_text=req.body_text,
        body_html=req.body_html if is_email else None,
        requested_by=req.requested_by,
        metadata_=req.metadata,
        max_attempts=settings.max_attempts,
        idempotency_key=idempotency_key,
        request_hash=digest,
    )
    msg.events.append(MessageEvent(event_type="queued", detail={}))
    db.add(msg)
    try:
        db.commit()
    except IntegrityError:
        # Lost a race with a concurrent request using the same idempotency key.
        db.rollback()
        existing = _find_existing(db, req.requested_by, idempotency_key) if idempotency_key else None
        if existing is None:
            raise
        return _check_replay(existing, digest), False
    return msg, True
