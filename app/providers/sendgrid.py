from app.config import Settings
from app.models import Message
from app.providers.base import SendResult, build_client, post


class SendGridProvider:
    """SendGrid v3 Mail Send: https://docs.sendgrid.com/api-reference/mail-send/mail-send"""

    name = "sendgrid"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = build_client(
            settings,
            base_url="https://api.sendgrid.com",
            headers={"Authorization": f"Bearer {settings.sendgrid_api_key}"},
        )

    def send(self, msg: Message) -> SendResult:
        content = [{"type": "text/plain", "value": msg.body_text}]
        if msg.body_html:
            content.append({"type": "text/html", "value": msg.body_html})
        payload = {
            "personalizations": [{"to": [{"email": msg.to_address}]}],
            "from": {"email": msg.from_address, "name": self.settings.default_from_name},
            "subject": msg.subject,
            "content": content,
            # Lets delivery webhooks be correlated back to our message id.
            "custom_args": {"message_id": str(msg.id), "requested_by": msg.requested_by},
        }
        resp = post(self.client, self.name, "/v3/mail/send", json=payload)
        return SendResult(self.name, resp.headers.get("X-Message-Id", ""))
