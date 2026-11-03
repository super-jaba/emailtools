import secrets
from typing import TYPE_CHECKING

from emailtool.infra.email.imap import ImapMailbox

if TYPE_CHECKING:
    from emailtool.config import Settings
    from emailtool.infra.email.base import Mailbox

DEV_DOMAIN = "emailtool.local"


def generate_dev_address() -> str:
    return f"agent-{secrets.token_hex(3)}@{DEV_DOMAIN}"


def build_mailbox(settings: Settings) -> Mailbox:
    address = settings.EMAIL_ADDRESS or generate_dev_address()
    password = settings.EMAIL_PASSWORD
    return ImapMailbox(
        address=address,
        password=password.get_secret_value() if password else address,
        host=settings.IMAP_HOST,
        port=settings.IMAP_PORT,
        ssl=settings.IMAP_SSL,
    )
