# Design Decisions

Goal: a fast MVP of a shared internal service that any team can call to send email/SMS to
members, providers, or customers from a company-owned sender identity. Vendor calls are mocked.

## 1. Async API + Postgres-backed queue (instead of Celery/Redis/SQS or a synchronous send)
`POST /v1/messages` validates, writes a `queued` row, and returns `202`. A separate worker
claims rows with `UPDATE ... WHERE id IN (SELECT ... FOR UPDATE SKIP LOCKED) RETURNING *`.

| Pros | Cons |
|---|---|
| No extra infra (Redis/RabbitMQ/SQS); Postgres is already required | Polling adds up to `WORKER_POLL_INTERVAL` latency and some DB load |
| Message record and queue entry are the same row, so there's no dual-write between a DB and a broker | Postgres-as-queue tops out somewhere around thousands of msgs/sec; SQS/Kafka is the move at scale |
| Easy to scale horizontally (`--scale worker=N`); SKIP LOCKED prevents double-claiming | No built-in priorities, fan-out, or dead-letter tooling (failed rows serve as the DLQ) |
| Queue state can be checked with plain SQL | |
| Callers don't block on vendor latency or outages; retries happen automatically | Callers poll `GET /v1/messages/{id}` for status (no callbacks/webhooks to callers yet) |

Rejected alternatives: **synchronous send** (simplest, but slow requests and a vendor outage
becomes our outage); **FastAPI BackgroundTasks** (in-process, so a crash loses messages).

## 2. Delivery semantics: at-least-once
The worker commits the claim (`sending`) before calling the vendor and commits the result after.
If a worker dies between the vendor call and the final commit, the reaper requeues the row
after `STALE_LOCK_SECONDS` and the message may be sent twice.

- **Pro:** messages are never silently dropped.
- **Con:** duplicates are possible in rare crash windows. Our message id goes to the vendor (SendGrid `custom_args`,
  Mailgun `v:message_id`) so duplicates can be traced. Exactly-once is impossible without vendor-side idempotency.

## 3. Retries: transient vs permanent errors
Vendor 429/5xx/timeouts → `TransientError` → exponential backoff with jitter
(`base * 2^(attempt-1) + rand(0, base)`), up to `MAX_ATTEMPTS`. Vendor 4xx → `PermanentError` → `failed` right away.

- **Pro:** no wasted retries on bad addresses, and we back off from a struggling vendor.
- **Con:** the HTTP-status-based classification is coarse; real vendors need per-error-code rules.

## 4. Idempotency keys
Optional `Idempotency-Key` header, unique per `(requested_by, idempotency_key)`. We store a SHA-256
of the request body. Same key + same body → returns the original message (`200`). Same key +
different body → `409`. Concurrent inserts are resolved by the unique constraint.

- **Pro:** callers can retry safely after timeouts without double-messaging patients. The DB enforces it, so it's race-safe.
- **Con:** keys never expire in the MVP (needs a TTL/cleanup job). Scoping relies on `requested_by`, which is unauthenticated (see 7).

## 5. Fixed sender identity
`from` comes from config (`DEFAULT_FROM_EMAIL`, `DEFAULT_SMS_FROM`), and callers cannot set it.

- **Pro:** one controlled, authenticated domain (SPF/DKIM/DMARC) protects deliverability and brand, and teams can't spoof.
- **Con:** teams can't use their own sender (e.g. `billing@`). Later we can add an allow-listed sender per team.

## 6. Vendor adapters with mocked HTTP
Each adapter (`SendGridProvider`, `MailgunProvider`, `TwilioProvider`) builds the real request
(URL, auth, payload shape) and sends it through `httpx`. With `MOCK_VENDORS=true` the client uses
`httpx.MockTransport`, so nothing leaves the process. Magic recipients trigger deterministic failures.

- **Pro:** the adapter code is real. Going live means flipping the flag and adding API keys. Tests and demos are deterministic.
- **Con:** the mocks can drift from real vendor behaviour (rate-limit headers, partial failures). Contract tests against vendor sandboxes would catch this.

One vendor per channel, chosen by config (`EMAIL_PROVIDER=sendgrid|mailgun`). **Pro:** simple.
**Con:** no automatic failover. A vendor outage burns retries. The `ProviderRegistry` is the place to add it.

## 7. No authentication (MVP)
`requested_by` is a free-text field in the request body.

- **Pro:** zero friction to onboard teams for the MVP.
- **Con:** anyone on the network can send as any team. **First thing to add before production:** per-team API
  keys or service-to-service auth (mTLS/JWT via the mesh/gateway), plus per-team rate limits.

## 8. Sync SQLAlchemy 2.0 + psycopg 3 (rather than async/asyncpg)
- **Pro:** simpler code and tests. FastAPI runs sync routes in a threadpool, which is fine at MVP volume.
- **Con:** lower concurrency per process than a fully async stack.

## 9. `create_all` on startup (rather than Alembic)
Guarded by a Postgres advisory lock so the api and multiple workers can start together.
- **Pro:** zero ceremony.
- **Con:** no migration history. Alembic must be added before the first schema change in prod.

## 10. One image for api and worker
- **Pro:** one build with shared models and adapters.
- **Con:** the image is slightly larger than each role needs. Services still scale independently in compose/k8s.

## 11. Message bodies stored in Postgres
- **Pro:** a full audit trail (`message_events`) and easy debugging and support.
- **Con:** PHI/PII at rest. Production needs encryption, a retention/purge policy, access controls, and
  log redaction (the mock vendor currently logs payloads for demo purposes).

## Future work (rough priority)
1. AuthN/Z per team + rate limiting/quotas
2. Opt-out / suppression lists and consent checks (CAN-SPAM, TCPA, HIPAA review)
3. Inbound vendor webhooks → `delivered`/`bounced`/`opened` statuses, plus outbound callbacks to calling teams
4. Templates (versioned, with variables) so teams don't build HTML themselves
5. Vendor failover / health-based routing
6. Scheduled sends (`send_at`, since `next_attempt_at` already supports it), batch/bulk endpoint
7. Alembic migrations, metrics (queue depth, send latency, failure rate), tracing, alerting
8. PII encryption + retention jobs, idempotency-key TTL
