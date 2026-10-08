from app.config import Settings
from app.models import Channel
from app.providers.base import Provider
from app.providers.mailgun import MailgunProvider
from app.providers.sendgrid import SendGridProvider
from app.providers.twilio import TwilioProvider

EMAIL_PROVIDERS = {"sendgrid": SendGridProvider, "mailgun": MailgunProvider}
SMS_PROVIDERS = {"twilio": TwilioProvider}


class ProviderRegistry:
    """Maps a channel to its configured vendor. Failover would slot in here."""

    def __init__(self, settings: Settings):
        self._providers: dict[Channel, Provider] = {
            Channel.email: EMAIL_PROVIDERS[settings.email_provider](settings),
            Channel.sms: SMS_PROVIDERS[settings.sms_provider](settings),
        }

    def get(self, channel: Channel) -> Provider:
        return self._providers[channel]
