# Messaging Service (MVP)

A shared internal service for sending **email and SMS** to members, providers, and customers from the
company's sender identity. Internal teams call one HTTP API. We handle vendor integration, retries,
idempotency, and the audit trail. Vendors (SendGrid, Mailgun, Twilio) are **mocked**, so no real messages are sent.

See **[DECISIONS.md](DECISIONS.md)** for the design choices and their trade-offs.

```
team ──POST /v1/messages──▶ api ──INSERT queued──▶ postgres ◀──SKIP LOCKED claim── worker(s) ──▶ SendGrid/Mailgun/Twilio (mock)
```

## Run it (Docker)
```bash
docker compose up --build                 # db + api + 1 worker
docker compose up --build --scale worker=3
```
- API: http://localhost:8000 (Swagger UI at http://localhost:8000/docs)
- Postgres: `127.0.0.1:5433` (host port 5433 avoids clashing with a local Postgres; override with `DB_HOST_PORT`)

## Use it
```bash
# Send an email
curl -X POST http://localhost:8000/v1/messages \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: results-ready-12345' \
  -d '{"channel":"email","recipient_type":"member","requested_by":"care-team",
       "to":"jane@example.com","subject":"Your results are ready",
       "body_text":"Log in to view your results.","body_html":"<p>Log in to view your results.</p>"}'
# -> 202 {"id":"...","status":"queued"}   (same key + same body again -> 200 same id; different body -> 409)

# Send an SMS
curl -X POST http://localhost:8000/v1/messages \
  -H 'Content-Type: application/json' \
  -d '{"channel":"sms","recipient_type":"provider","requested_by":"scheduling",
       "to":"+15551234567","body_text":"Reminder: your shift starts at 9am."}'

# Check status + event history
curl http://localhost:8000/v1/messages/<id>

# List / filter
curl 'http://localhost:8000/v1/messages?status=failed&requested_by=care-team&limit=20'
```

| Field | Notes |
|---|---|
| `channel` | `email` or `sms` |
| `recipient_type` | `member`, `provider`, or `customer` |
| `requested_by` | calling team (unauthenticated in the MVP) |
| `to` | email address, or E.164 phone number for SMS |
| `subject`, `body_html` | email only (`subject` is required for email) |
| `body_text` | required (SMS max 1600 chars) |
| `metadata` | free-form JSON for the caller's own correlation |

Statuses: `queued → sending → sent | failed` (a transient failure goes back to `queued` with backoff).

### Mock vendor test recipients
| Recipient | Behaviour |
|---|---|
| `transient-fail@example.com`, `+15005550001` | 503: retried with backoff, then `failed` after `MAX_ATTEMPTS` |
| `bounce@example.com`, `+15005550002` | 400: `failed` right away, not retried |
| anything else | success (or random 503 at `MOCK_FAILURE_RATE`) |

## Configuration
Environment variables (see `.env.example`): `EMAIL_PROVIDER` (`sendgrid`|`mailgun`), `SMS_PROVIDER`,
`DEFAULT_FROM_EMAIL`, `DEFAULT_SMS_FROM`, `MOCK_VENDORS`, `MOCK_FAILURE_RATE`, `MAX_ATTEMPTS`.
```bash
MOCK_FAILURE_RATE=0.3 EMAIL_PROVIDER=mailgun docker compose up --build
```

## Local development (uv)
```bash
uv sync
docker compose up -d db                       # Postgres only
uv run uvicorn app.main:app --reload          # API on :8000
uv run python -m app.worker                   # worker
uv run pytest                                 # uses the messaging_test database
```

## Layout
```
app/
  main.py               FastAPI app + /health
  api/messages.py       HTTP routes
  services/messages.py  create + idempotency logic
  models.py             messages, message_events
  worker.py             claim → send → record, retries, stale-lock reaper
  providers/            SendGrid / Mailgun / Twilio adapters + mock transport
tests/                  API + worker tests against real Postgres
```
