"""In-process fake vendor APIs. No network calls leave the container.

Magic recipients give deterministic failures for tests/demos:
  transient-fail@example.com / +15005550001 -> 503 (retried)
  bounce@example.com         / +15005550002 -> 400 (permanent)
"""

import json
import logging
import random
import uuid
from urllib.parse import parse_qs

import httpx

log = logging.getLogger("mock_vendor")

TRANSIENT_RECIPIENTS = {"transient-fail@example.com", "+15005550001"}
PERMANENT_RECIPIENTS = {"bounce@example.com", "+15005550002"}


def _recipient(request: httpx.Request) -> str:
    body = request.content.decode()
    host = request.url.host
    if host == "api.sendgrid.com":
        return json.loads(body)["personalizations"][0]["to"][0]["email"]
    form = parse_qs(body)
    if host == "api.mailgun.net":
        return form["to"][0]
    if host == "api.twilio.com":
        return form["To"][0]
    raise ValueError(f"unknown mock vendor host {host}")


def _success(host: str) -> httpx.Response:
    if host == "api.sendgrid.com":
        return httpx.Response(202, headers={"X-Message-Id": f"sg_{uuid.uuid4().hex[:22]}"})
    if host == "api.mailgun.net":
        mid = f"<{uuid.uuid4().hex}@mg.company.com>"
        return httpx.Response(200, json={"id": mid, "message": "Queued. Thank you."})
    return httpx.Response(201, json={"sid": f"SM{uuid.uuid4().hex}", "status": "queued"})


def mock_transport(failure_rate: float = 0.0) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        host = request.url.host
        to = _recipient(request)
        log.info("mock %s %s to=%s payload=%s", request.method, request.url, to, request.content.decode()[:500])

        if to in PERMANENT_RECIPIENTS:
            return httpx.Response(400, json={"errors": [{"message": f"invalid recipient {to}"}]})
        if to in TRANSIENT_RECIPIENTS or random.random() < failure_rate:
            return httpx.Response(503, json={"errors": [{"message": "service unavailable"}]})
        return _success(host)

    return httpx.MockTransport(handler)
