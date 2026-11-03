import asyncio
from collections import defaultdict
from contextlib import contextmanager
from itertools import batched
from typing import TYPE_CHECKING, Any, cast

from imapclient import IMAPClient
from imapclient.exceptions import IMAPClientError
from imapclient.imapclient import SENT

from emailtool.infra.email.base import (
    AttachmentNotFound,
    Mailbox,
    MailboxError,
    MessageNotFound,
)
from emailtool.infra.email.models import (
    AttachmentContent,
    EmailMessage,
    EmailThread,
    MessageFilter,
)
from emailtool.infra.email.parsing import (
    AttachmentRef,
    MessageRef,
    build_summary,
    parse_body,
    parse_thread_headers,
    read_attachment,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from emailtool.infra.email.models import MessageSummary

INBOX = "INBOX"
MAX_THREAD_MESSAGES = 200
TIMEOUT_SECONDS = 30
FETCH_BATCH_SIZE = 100

SUMMARY_FIELDS = ["ENVELOPE", "FLAGS", "INTERNALDATE", "BODYSTRUCTURE"]
THREAD_HEADERS = "HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES)"
THREAD_HEADERS_FETCH = f"BODY.PEEK[{THREAD_HEADERS}]"
THREAD_HEADERS_KEY = f"BODY[{THREAD_HEADERS}]".encode()
THREAD_SEARCH_HEADERS = ("Message-ID", "References", "In-Reply-To")


def _search(client: IMAPClient, criteria: list[Any]) -> list[int]:
    return client.search(criteria, charset="UTF-8")  # pyright: ignore[reportArgumentType]


def _raw(item: dict[bytes, Any], key: bytes) -> bytes:
    return cast("bytes", item[key])


def _build_criteria(filters: MessageFilter) -> list[Any]:
    criteria: list[Any] = ["UNDELETED"]
    if filters.subject:
        criteria += ["SUBJECT", filters.subject]
    if filters.body:
        criteria += ["BODY", filters.body]
    if filters.since:
        criteria += ["SINCE", filters.since]
    if filters.before:
        criteria += ["BEFORE", filters.before]
    if filters.unread_only:
        criteria.append("UNSEEN")
    return criteria


def _matches(summary: MessageSummary, filters: MessageFilter) -> bool:
    # FROM/TO/CC search semantics differ between servers (GreenMail only matches
    # whole addresses), so substring matching on addresses happens client-side.
    if filters.sender and filters.sender.lower() not in (summary.sender or "").lower():
        return False
    if filters.recipient:
        needle = filters.recipient.lower()
        if not any(needle in address.lower() for address in summary.to + summary.cc):
            return False
    return summary.has_attachments or not filters.has_attachments


def _select_ref(client: IMAPClient, ref: MessageRef) -> None:
    try:
        info = client.select_folder(ref.folder)
    except IMAPClientError as e:
        raise MessageNotFound(f"Folder not found: {ref.folder}") from e
    if info[b"UIDVALIDITY"] != ref.uid_validity:
        raise MessageNotFound(f"Stale message reference in {ref.folder}")


def _decode_message_ref(message_id: str) -> MessageRef:
    try:
        return MessageRef.decode(message_id)
    except (ValueError, TypeError) as e:
        raise MessageNotFound(f"Invalid message id: {message_id}") from e


def _decode_attachment_ref(attachment_id: str) -> AttachmentRef:
    try:
        return AttachmentRef.decode(attachment_id)
    except (ValueError, TypeError) as e:
        raise AttachmentNotFound(f"Invalid attachment id: {attachment_id}") from e


def _list_messages(client: IMAPClient, filters: MessageFilter) -> list[MessageSummary]:
    info = client.select_folder(filters.folder)
    uid_validity = info[b"UIDVALIDITY"]
    uids = sorted(_search(client, _build_criteria(filters)), reverse=True)

    summaries: list[MessageSummary] = []
    for batch in batched(uids, FETCH_BATCH_SIZE):
        items = client.fetch(list(batch), SUMMARY_FIELDS)
        for uid in batch:
            if uid not in items:
                continue
            summary = build_summary(
                MessageRef(filters.folder, uid_validity, uid), items[uid]
            )
            if _matches(summary, filters):
                summaries.append(summary)
                if len(summaries) == filters.limit:
                    return summaries
    return summaries


def _thread_folders(client: IMAPClient, start: MessageRef) -> list[str]:
    folders = [start.folder, INBOX]
    sent = client.find_special_folder(SENT)
    if sent:
        folders.append(sent)
    return list(dict.fromkeys(folders))


def _find_related(
    client: IMAPClient, target: str
) -> Iterator[tuple[int, str, set[str]]]:
    uids: set[int] = set()
    for header in THREAD_SEARCH_HEADERS:
        uids.update(_search(client, ["HEADER", header, target]))
    if not uids:
        return

    for uid, item in client.fetch(sorted(uids), [THREAD_HEADERS_FETCH]).items():
        own, related = parse_thread_headers(_raw(item, THREAD_HEADERS_KEY))
        # HEADER search is a substring match, so re-check for an exact hit.
        if own is not None and (own == target or target in related):
            yield uid, own, related


def _collect_thread(client: IMAPClient, start: MessageRef) -> list[tuple[str, int]]:
    _select_ref(client, start)
    items = client.fetch([start.uid], [THREAD_HEADERS_FETCH])
    if start.uid not in items:
        raise MessageNotFound(f"Message not found: {start.uid}")

    own, related = parse_thread_headers(_raw(items[start.uid], THREAD_HEADERS_KEY))
    if own is None:
        return [(start.folder, start.uid)]

    # Keyed by Message-ID, so a copy in a second folder doesn't count twice.
    members = {own: (start.folder, start.uid)}
    folders = _thread_folders(client, start)
    visited: set[str] = set()
    frontier = {own} | related

    while frontier and len(members) < MAX_THREAD_MESSAGES:
        visited |= frontier
        discovered: set[str] = set()
        for folder in folders:
            client.select_folder(folder)
            for target in frontier:
                for uid, message_id, references in _find_related(client, target):
                    members.setdefault(message_id, (folder, uid))
                    discovered |= {message_id} | references
        frontier = discovered - visited

    return list(members.values())[:MAX_THREAD_MESSAGES]


def _get_thread(client: IMAPClient, message_id: str) -> EmailThread:
    members = _collect_thread(client, _decode_message_ref(message_id))

    uids_by_folder: defaultdict[str, list[int]] = defaultdict(list)
    for folder, uid in members:
        uids_by_folder[folder].append(uid)

    messages: list[EmailMessage] = []
    for folder, uids in uids_by_folder.items():
        uid_validity = client.select_folder(folder)[b"UIDVALIDITY"]
        for uid, item in client.fetch(
            sorted(uids), [*SUMMARY_FIELDS, "BODY[]"]
        ).items():
            ref = MessageRef(folder, uid_validity, uid)
            body_text, body_html, attachments = parse_body(_raw(item, b"BODY[]"), ref)
            messages.append(
                EmailMessage(
                    **build_summary(ref, item).model_dump(),
                    body_text=body_text,
                    body_html=body_html,
                    attachments=attachments,
                )
            )

    messages.sort(key=lambda message: message.date)
    return EmailThread(messages=messages)


def _get_attachment(client: IMAPClient, attachment_id: str) -> AttachmentContent:
    ref = _decode_attachment_ref(attachment_id)
    _select_ref(client, ref.message)

    # The whole message is fetched because part fetches can't be relied on:
    # GreenMail fails BODY[1.MIME] on single-part messages and answers
    # out-of-range sections with the message body.
    items = client.fetch([ref.message.uid], ["BODY[]"])
    if ref.message.uid not in items:
        raise MessageNotFound(f"Message not found: {ref.message.uid}")

    found = read_attachment(_raw(items[ref.message.uid], b"BODY[]"), ref)
    if found is None:
        raise AttachmentNotFound(f"Attachment not found: {ref.index}")
    info, data = found
    return AttachmentContent(**info.model_dump(), data=data)


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

    async def get_attachment(self, attachment_id: str) -> AttachmentContent:
        return await self._run(_get_attachment, attachment_id)

    @contextmanager
    def _connect(self) -> Iterator[IMAPClient]:
        client = IMAPClient(
            self._host, port=self._port, ssl=self._ssl, timeout=TIMEOUT_SECONDS
        )
        client.normalise_times = False  # Keep the timezone on parsed dates
        try:
            client.login(self._address, self._password)
            yield client
        finally:
            client.shutdown()

    async def _run[T, A](
        self, operation: Callable[[IMAPClient, A], T], argument: A
    ) -> T:
        def call() -> T:
            try:
                with self._connect() as client:
                    return operation(client, argument)
            except (IMAPClientError, OSError) as e:
                raise MailboxError(f"IMAP request failed: {e}") from e

        return await asyncio.to_thread(call)
