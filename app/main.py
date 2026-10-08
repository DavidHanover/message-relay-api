import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.messages import router as messages_router
from app.db import get_db, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Messaging Service",
    description="Shared internal service for sending email/SMS on behalf of the company.",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(messages_router)


@app.get("/health", tags=["ops"])
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}
