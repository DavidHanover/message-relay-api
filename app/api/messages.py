import uuid

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.db import get_db
from app.models import Channel, Message, MessageStatus
from app.schemas import MessageDetailOut, MessageOut, SendMessageRequest, SendMessageResponse
from app.services.messages import IdempotencyConflict, create_message

router = APIRouter(prefix="/v1/messages", tags=["messages"])


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=SendMessageResponse)
def send_message(
    response: Response,
    req: SendMessageRequest = Body(...),
    idempotency_key: str | None = Header(default=None, max_length=255),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    try:
        msg, created = create_message(db, req, settings, idempotency_key)
    except IdempotencyConflict:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Idempotency-Key was already used with a different request body"
        )
    if not created:
        response.status_code = status.HTTP_200_OK
    return SendMessageResponse(id=msg.id, status=msg.status)


@router.get("/{message_id}", response_model=MessageDetailOut)
def get_message(message_id: uuid.UUID, db: Session = Depends(get_db)):
    msg = db.scalar(select(Message).options(selectinload(Message.events)).where(Message.id == message_id))
    if msg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return msg


@router.get("", response_model=list[MessageOut])
def list_messages(
    status_: MessageStatus | None = Query(default=None, alias="status"),
    channel: Channel | None = None,
    requested_by: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(Message).order_by(Message.created_at.desc()).limit(limit)
    if status_:
        stmt = stmt.where(Message.status == status_)
    if channel:
        stmt = stmt.where(Message.channel == channel)
    if requested_by:
        stmt = stmt.where(Message.requested_by == requested_by)
    return db.scalars(stmt).all()
