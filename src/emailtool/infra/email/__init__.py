from emailtool.infra.email.base import (
    AttachmentNotFound,
    Mailbox,
    MailboxError,
    MessageNotFound,
)
from emailtool.infra.email.factory import build_mailbox, generate_dev_address
from emailtool.infra.email.imap import ImapMailbox
from emailtool.infra.email.models import (
    AttachmentContent,
    AttachmentInfo,
    EmailMessage,
    EmailThread,
    MessageFilter,
    MessageSummary,
)

__all__ = [
    "AttachmentContent",
    "AttachmentInfo",
    "AttachmentNotFound",
    "EmailMessage",
    "EmailThread",
    "ImapMailbox",
    "Mailbox",
    "MailboxError",
    "MessageFilter",
    "MessageNotFound",
    "MessageSummary",
    "build_mailbox",
    "generate_dev_address",
]
