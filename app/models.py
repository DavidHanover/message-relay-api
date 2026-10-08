import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Channel(str, enum.Enum):
    email = "email"
    sms = "sms"


class RecipientType(str, enum.Enum):
    member = "member"
    provider = "provider"
    customer = "customer"


class MessageStatus(str, enum.Enum):
    queued = "queued"
    sending = "sending"
    sent = "sent"
    failed = "failed"


def _enum(e: type[enum.Enum], name: str) -> Enum:
    return Enum(e, name=name, values_callable=lambda x: [m.value for m in x])


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        UniqueConstraint("requested_by", "idempotency_key", name="uq_messages_idempotency"),
        Index("ix_messages_status_next_attempt", "status", "next_attempt_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[Channel] = mapped_column(_enum(Channel, "channel"))
    recipient_type: Mapped[RecipientType] = mapped_column(_enum(RecipientType, "recipient_type"))
    to_address: Mapped[str] = mapped_column(String(320))
    from_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(998))
    body_text: Mapped[str] = mapped_column(Text)
    body_html: Mapped[str | None] = mapped_column(Text)
    requested_by: Mapped[str] = mapped_column(String(100), index=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)

    status: Mapped[MessageStatus] = mapped_column(
        _enum(MessageStatus, "message_status"), default=MessageStatus.queued
    )
    provider: Mapped[str | None] = mapped_column(String(50))
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    attempts: Mapped[int] = mapped_column(default=0)
    max_attempts: Mapped[int]
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)

    idempotency_key: Mapped[str | None] = mapped_column(String(255))
    request_hash: Mapped[str] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    events: Mapped[list["MessageEvent"]] = relationship(
        back_populates="message", order_by="MessageEvent.id", cascade="all, delete-orphan"
    )


class MessageEvent(Base):
    __tablename__ = "message_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("messages.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    message: Mapped[Message] = relationship(back_populates="events")
