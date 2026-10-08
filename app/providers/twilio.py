from app.config import Settings
from app.models import Message
from app.providers.base import SendResult, build_client, post


class TwilioProvider:
    """Twilio Programmable Messaging: https://www.twilio.com/docs/messaging/api/message-resource"""

    name = "twilio"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = build_client(
            settings,
            base_url="https://api.twilio.com",
            auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        )

    def send(self, msg: Message) -> SendResult:
        data = {"To": msg.to_address, "From": msg.from_address, "Body": msg.body_text}
        url = f"/2010-04-01/Accounts/{self.settings.twilio_account_sid}/Messages.json"
        resp = post(self.client, self.name, url, data=data)
        return SendResult(self.name, resp.json()["sid"])
