import asyncio
import imaplib
from typing import TYPE_CHECKING

from imap_tools import AND, OR, H, MailBox, MailBoxUnencrypted
from imap_tools.errors import ImapToolsError

from emailtool.infra.email.base import (
    AttachmentNotFound,
    Mailbox,
    MailboxError,
    MessageNotFound,
)
from emailtool.infra.email.models import (
    AttachmentContent,
    AttachmentInfo,
    EmailMessage,
    EmailThread,
    MessageFilter,
    MessageSummary,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from imap_tools import BaseMailBox, EmailAddress, MailMessage

CHARSET = "UTF-8"


def _header(msg: MailMessage, name: str) -> str:
    return (msg.headers.get(name.lower()) or ("",))[0].strip()


def _has_address(addresses: tuple[EmailAddress, ...], needle: str) -> bool:
    needle = needle.lower()
    return any(needle in f"{a.name} {a.email}".lower() for a in addresses)


def _matches(msg: MailMessage, filters: MessageFilter) -> bool:
    # Done client-side: FROM/TO/CC search semantics differ between servers
    # (GreenMail only matches whole addresses).
    if filters.sender and not _has_address(
        (msg.from_values,) if msg.from_values else (), filters.sender
    ):
        return False
    if filters.recipient and not _has_address(
        msg.to_values + msg.cc_values, filters.recipient
    ):
        return False
    return bool(msg.attachments) or not filters.has_attachments


def _to_summary(msg: MailMessage) -> MessageSummary:
    return MessageSummary(
        message_id=_header(msg, "Message-ID") or None,
        sender=msg.from_values.full if msg.from_values else None,
        to=[a.full for a in msg.to_values],
        cc=[a.full for a in msg.cc_values],
        subject=msg.subject,
        date=msg.date,
        is_read="\\Seen" in msg.flags,
        has_attachments=bool(msg.attachments),
    )


def _to_message(msg: MailMessage) -> EmailMessage:
    return EmailMessage(
        **_to_summary(msg).model_dump(),
        body_text=msg.text or None,
        body_html=msg.html or None,
        attachments=[
            AttachmentInfo(
                filename=a.filename, content_type=a.content_type, size=a.size
            )
            for a in msg.attachments
        ],
    )


def _folders(mailbox: BaseMailBox) -> list[str]:
    sent = [
        f.name
        for f in mailbox.folder.list()
        if "\\Sent" in f.flags or f.name.lower() == "sent"
    ]
    return ["INBOX", *sent]


def _find(mailbox: BaseMailBox, message_id: str) -> MailMessage:
    for folder in _folders(mailbox):
        mailbox.folder.set(folder)
        criteria = AND(header=H("Message-ID", message_id))
        for msg in mailbox.fetch(criteria, CHARSET, limit=1):
            return msg
    raise MessageNotFound(f"Message not found: {message_id}")


def _list_messages(
    mailbox: BaseMailBox, filters: MessageFilter
) -> list[MessageSummary]:
    mailbox.folder.set(filters.folder)
    conditions = {
        "subject": filters.subject,
        "body": filters.body,
        "date_gte": filters.since,
        "date_lt": filters.before,
        "seen": False if filters.unread_only else None,
    }
    conditions = {k: v for k, v in conditions.items() if v is not None}
    criteria = AND(**conditions) if conditions else "ALL"

    summaries: list[MessageSummary] = []
    for msg in mailbox.fetch(criteria, CHARSET, reverse=True, mark_seen=False):
        if _matches(msg, filters):
            summaries.append(_to_summary(msg))
            if len(summaries) == filters.limit:
                break
    return summaries


def _get_thread(mailbox: BaseMailBox, message_id: str) -> EmailThread:
    # Replies list their ancestors in References, root first.
    start = _find(mailbox, message_id)
    references = _header(start, "References").split()
    root = references[0] if references else message_id

    criteria = OR(header=[H("Message-ID", root), H("References", root)])
    messages: dict[str, EmailMessage] = {}
    for folder in _folders(mailbox):
        mailbox.folder.set(folder)
        for msg in mailbox.fetch(criteria, CHARSET):
            message = _to_message(msg)
            messages.setdefault(message.message_id or "", message)

    return EmailThread(messages=sorted(messages.values(), key=lambda m: m.date))


def _get_attachment(
    mailbox: BaseMailBox, message_id: str, filename: str
) -> AttachmentContent:
    for a in _find(mailbox, message_id).attachments:
        if a.filename == filename:
            return AttachmentContent(
                filename=a.filename,
                content_type=a.content_type,
                size=a.size,
                data=a.payload,
            )
    raise AttachmentNotFound(f"Attachment not found: {filename}")


class ImapMailbox(Mailbox):
    def __init__(
        self,
        address: str,
        password: str,
        host: str,
        port: int,
        ssl: bool,
    ) -> None:
        self._address = address
        self._password = password
        self._host = host
        self._port = port
        self._ssl = ssl

    @property
    def address(self) -> str:
        return self._address

    async def list_messages(
        self, filters: MessageFilter | None = None
    ) -> list[MessageSummary]:
        return await self._run(_list_messages, filters or MessageFilter())

    async def get_thread(self, message_id: str) -> EmailThread:
        return await self._run(_get_thread, message_id)

    async def get_attachment(self, message_id: str, filename: str) -> AttachmentContent:
        return await self._run(_get_attachment, message_id, filename)

    async def _run[T, *Args](
        self, operation: Callable[[BaseMailBox, *Args], T], *args: *Args
    ) -> T:
        def call() -> T:
            mailbox_class = MailBox if self._ssl else MailBoxUnencrypted
            try:
                with mailbox_class(self._host, self._port).login(
                    self._address, self._password, initial_folder=None
                ) as mailbox:
                    return operation(mailbox, *args)
            except (ImapToolsError, imaplib.IMAP4.error, OSError) as e:
                raise MailboxError(f"IMAP request failed: {e}") from e

        return await asyncio.to_thread(call)
