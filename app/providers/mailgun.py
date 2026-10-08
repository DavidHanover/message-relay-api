from app.config import Settings
from app.models import Message
from app.providers.base import SendResult, build_client, post


class MailgunProvider:
    """Mailgun Messages API: https://documentation.mailgun.com/docs/mailgun/api-reference/"""

    name = "mailgun"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = build_client(
            settings, base_url="https://api.mailgun.net", auth=("api", settings.mailgun_api_key)
        )

    def send(self, msg: Message) -> SendResult:
        data = {
            "from": f"{self.settings.default_from_name} <{msg.from_address}>",
            "to": msg.to_address,
            "subject": msg.subject,
            "text": msg.body_text,
            "v:message_id": str(msg.id),
        }
        if msg.body_html:
            data["html"] = msg.body_html
        resp = post(self.client, self.name, f"/v3/{self.settings.mailgun_domain}/messages", data=data)
        return SendResult(self.name, resp.json()["id"])
