import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Channel, MessageStatus, RecipientType


class _BaseSend(BaseModel):
    recipient_type: RecipientType
    requested_by: str = Field(min_length=1, max_length=100, description="Calling team, e.g. 'billing'")
    body_text: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EmailSendRequest(_BaseSend):
    channel: Literal["email"]
    to: EmailStr
    subject: str = Field(min_length=1, max_length=998)
    body_html: str | None = None


class SmsSendRequest(_BaseSend):
    channel: Literal["sms"]
    to: str = Field(pattern=r"^\+[1-9]\d{1,14}$", description="E.164 phone number")
    body_text: str = Field(min_length=1, max_length=1600)


SendMessageRequest = Annotated[EmailSendRequest | SmsSendRequest, Field(discriminator="channel")]


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: str
    detail: dict[str, Any]
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    channel: Channel
    recipient_type: RecipientType
    to_address: str
    from_address: str
    subject: str | None
    requested_by: str
    metadata: dict[str, Any] = Field(validation_alias="metadata_")
    status: MessageStatus
    provider: str | None
    provider_message_id: str | None
    attempts: int
    max_attempts: int
    next_attempt_at: datetime
    last_error: str | None
    idempotency_key: str | None
    created_at: datetime
    updated_at: datetime


class MessageDetailOut(MessageOut):
    events: list[EventOut]


class SendMessageResponse(BaseModel):
    id: uuid.UUID
    status: MessageStatus
