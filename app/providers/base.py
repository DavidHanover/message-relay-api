from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings
from app.models import Message


@dataclass
class SendResult:
    provider: str
    provider_message_id: str


class ProviderError(Exception):
    pass


class TransientError(ProviderError):
    """Worth retrying: vendor 429/5xx, timeouts, connection errors."""


class PermanentError(ProviderError):
    """Retrying won't help: invalid recipient, rejected payload, auth failure."""


class Provider(Protocol):
    name: str

    def send(self, msg: Message) -> SendResult: ...


def build_client(settings: Settings, **kwargs) -> httpx.Client:
    """HTTP client for vendor calls; routed to the in-process mock when MOCK_VENDORS is on."""
    if settings.mock_vendors:
        from app.providers.mock_transport import mock_transport

        kwargs["transport"] = mock_transport(settings.mock_failure_rate)
    return httpx.Client(timeout=10.0, **kwargs)


def post(client: httpx.Client, provider: str, url: str, **kwargs) -> httpx.Response:
    """POST to a vendor and translate failures into Transient/PermanentError."""
    try:
        resp = client.post(url, **kwargs)
    except httpx.TransportError as e:
        raise TransientError(f"{provider}: {type(e).__name__}: {e}") from e
    if resp.status_code == 429 or resp.status_code >= 500:
        raise TransientError(f"{provider}: HTTP {resp.status_code}: {resp.text[:200]}")
    if resp.status_code >= 400:
        raise PermanentError(f"{provider}: HTTP {resp.status_code}: {resp.text[:200]}")
    return resp
