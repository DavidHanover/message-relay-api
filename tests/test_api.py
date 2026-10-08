import uuid

from tests.conftest import email_payload, sms_payload


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_send_email_queues_message(client):
    resp = client.post("/v1/messages", json=email_payload())
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"

    detail = client.get(f"/v1/messages/{body['id']}").json()
    assert detail["from_address"] == "notifications@company.com"
    assert detail["to_address"] == "jane@example.com"
    assert detail["recipient_type"] == "member"
    assert [e["event_type"] for e in detail["events"]] == ["queued"]


def test_send_sms_queues_message(client):
    resp = client.post("/v1/messages", json=sms_payload())
    assert resp.status_code == 202
    detail = client.get(f"/v1/messages/{resp.json()['id']}").json()
    assert detail["channel"] == "sms"
    assert detail["subject"] is None


def test_validation_errors(client):
    assert client.post("/v1/messages", json=email_payload(to="not-an-email")).status_code == 422
    assert client.post("/v1/messages", json=email_payload(subject=None)).status_code == 422
    assert client.post("/v1/messages", json=sms_payload(to="555-1234")).status_code == 422
    assert client.post("/v1/messages", json=sms_payload(channel="fax")).status_code == 422
    assert client.post("/v1/messages", json=email_payload(recipient_type="stranger")).status_code == 422


def test_idempotent_replay_returns_same_message(client):
    headers = {"Idempotency-Key": "order-123-confirmation"}
    first = client.post("/v1/messages", json=email_payload(), headers=headers)
    second = client.post("/v1/messages", json=email_payload(), headers=headers)
    assert first.status_code == 202
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/v1/messages").json()) == 1


def test_idempotency_key_reuse_with_different_body_conflicts(client):
    headers = {"Idempotency-Key": "k1"}
    client.post("/v1/messages", json=email_payload(), headers=headers)
    resp = client.post("/v1/messages", json=email_payload(body_text="different"), headers=headers)
    assert resp.status_code == 409


def test_idempotency_keys_are_scoped_per_team(client):
    headers = {"Idempotency-Key": "shared-key"}
    a = client.post("/v1/messages", json=email_payload(requested_by="billing"), headers=headers)
    b = client.post("/v1/messages", json=email_payload(requested_by="care-team"), headers=headers)
    assert a.status_code == b.status_code == 202
    assert a.json()["id"] != b.json()["id"]


def test_list_filters(client):
    client.post("/v1/messages", json=email_payload())
    client.post("/v1/messages", json=sms_payload())
    assert len(client.get("/v1/messages").json()) == 2
    assert [m["channel"] for m in client.get("/v1/messages?channel=sms").json()] == ["sms"]
    assert len(client.get("/v1/messages?requested_by=care-team").json()) == 1
    assert client.get("/v1/messages?status=sent").json() == []


def test_get_unknown_message_404(client):
    assert client.get(f"/v1/messages/{uuid.uuid4()}").status_code == 404
