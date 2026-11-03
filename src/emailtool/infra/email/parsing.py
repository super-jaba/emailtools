import base64
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from email import policy
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from email.parser import BytesHeaderParser, BytesParser
from typing import TYPE_CHECKING, Any, Self, cast

from emailtool.infra.email.models import AttachmentInfo, MessageSummary

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from email.message import EmailMessage as MimeMessage

    from imapclient.response_types import Address

_MESSAGE_ID = re.compile(r"<[!-;=?-~]+>")

# Index of the disposition field in a non-multipart BODYSTRUCTURE (RFC 3501 7.4.2).
_DISPOSITION_INDEX = 8
_TEXT_DISPOSITION_INDEX = 9
_RFC822_DISPOSITION_INDEX = 11


def _encode_ref(*parts: str | int) -> str:
    return base64.urlsafe_b64encode(json.dumps(parts).encode()).decode()


def _decode_ref(value: str) -> list[Any]:
    parts = json.loads(base64.urlsafe_b64decode(value.encode()))
    if not isinstance(parts, list):
        raise TypeError("Not a mailbox reference")
    return parts


@dataclass(frozen=True)
class MessageRef:
    folder: str
    uid_validity: int
    uid: int

    def encode(self) -> str:
        return _encode_ref(self.folder, self.uid_validity, self.uid)

    @classmethod
    def decode(cls, value: str) -> Self:
        folder, uid_validity, uid = _decode_ref(value)
        return cls(folder, uid_validity, uid)


@dataclass(frozen=True)
class AttachmentRef:
    message: MessageRef
    index: int

    def encode(self) -> str:
        message = self.message
        return _encode_ref(
            message.folder, message.uid_validity, message.uid, self.index
        )

    @classmethod
    def decode(cls, value: str) -> Self:
        folder, uid_validity, uid, index = _decode_ref(value)
        return cls(MessageRef(folder, uid_validity, uid), index)


def _decode_words(value: bytes | None) -> str:
    if value is None:
        return ""
    text = value.decode("utf-8", "replace")
    try:
        return str(make_header(decode_header(text)))
    except LookupError, ValueError, HeaderParseError:
        return text


def _format_addresses(addresses: tuple[Address, ...] | None) -> list[str]:
    formatted = []
    for address in addresses or ():
        if address.mailbox is None or address.host is None:
            continue  # RFC 3501 group syntax markers
        email = f"{address.mailbox.decode('utf-8', 'replace')}@{address.host.decode('utf-8', 'replace')}"
        name = _decode_words(address.name)
        formatted.append(f"{name} <{email}>" if name else email)
    return formatted


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _has_attachment_params(params: Any) -> bool:
    if not isinstance(params, tuple):
        return False
    keys = (key.lower() for key in params[::2] if isinstance(key, bytes))
    return any(key.startswith((b"filename", b"name")) for key in keys)


def has_attachment_part(structure: Sequence[Any]) -> bool:
    if isinstance(structure[0], list):  # Multipart: (children, subtype, ...)
        return any(has_attachment_part(child) for child in structure[0])

    maintype, subtype = structure[0].lower(), structure[1].lower()
    if maintype == b"text":
        index = _TEXT_DISPOSITION_INDEX
    elif (maintype, subtype) == (b"message", b"rfc822"):
        index = _RFC822_DISPOSITION_INDEX
    else:
        index = _DISPOSITION_INDEX

    disposition = structure[index] if len(structure) > index else None
    if isinstance(disposition, tuple) and (
        disposition[0].lower() == b"attachment"
        or _has_attachment_params(disposition[1])
    ):
        return True
    return _has_attachment_params(structure[2])


def build_summary(ref: MessageRef, item: dict[bytes, Any]) -> MessageSummary:
    envelope = item[b"ENVELOPE"]
    senders = _format_addresses(envelope.from_)
    message_id = envelope.message_id
    return MessageSummary(
        id=ref.encode(),
        message_id_header=message_id.decode("utf-8", "replace") if message_id else None,
        sender=senders[0] if senders else None,
        to=_format_addresses(envelope.to),
        cc=_format_addresses(envelope.cc),
        subject=_decode_words(envelope.subject),
        date=_as_utc(envelope.date or item[b"INTERNALDATE"]),
        is_read=b"\\Seen" in item[b"FLAGS"],
        has_attachments=has_attachment_part(item[b"BODYSTRUCTURE"]),
    )


def parse_thread_headers(raw: bytes) -> tuple[str | None, set[str]]:
    headers = BytesHeaderParser(policy=policy.compat32).parsebytes(raw)
    own = _MESSAGE_ID.findall(str(headers.get("Message-ID", "")))
    related = _MESSAGE_ID.findall(
        f"{headers.get('In-Reply-To', '')} {headers.get('References', '')}"
    )
    return (own[0] if own else None), set(related)


def _parse_mime(raw: bytes) -> MimeMessage:
    return cast("MimeMessage", BytesParser(policy=policy.default).parsebytes(raw))


def _leaf_parts(part: MimeMessage) -> Iterator[MimeMessage]:
    if part.get_content_maintype() == "multipart":
        for child in part.iter_parts():
            yield from _leaf_parts(cast("MimeMessage", child))
    else:
        yield part


def _is_attachment(part: MimeMessage) -> bool:
    return (
        part.get_content_disposition() == "attachment"
        or part.get_filename() is not None
    )


def _part_bytes(part: MimeMessage) -> bytes:
    payload = part.get_payload(decode=True)
    if isinstance(payload, bytes):
        return payload
    # message/rfc822 attachments stay parsed: serialize the nested message back.
    return part.get_payload(0).as_bytes()  # pyright: ignore[reportAttributeAccessIssue]


def _part_text(part: MimeMessage) -> str:
    data = _part_bytes(part)
    try:
        return data.decode(part.get_content_charset("utf-8"), "replace")
    except LookupError:
        return data.decode("utf-8", "replace")


def _attachment_info(ref: MessageRef, index: int, part: MimeMessage) -> AttachmentInfo:
    return AttachmentInfo(
        id=AttachmentRef(ref, index).encode(),
        filename=part.get_filename(),
        content_type=part.get_content_type(),
        size=len(_part_bytes(part)),
    )


def parse_body(
    raw: bytes, ref: MessageRef
) -> tuple[str | None, str | None, list[AttachmentInfo]]:
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[AttachmentInfo] = []

    for part in _leaf_parts(_parse_mime(raw)):
        if _is_attachment(part):
            attachments.append(_attachment_info(ref, len(attachments), part))
        elif part.get_content_type() == "text/plain" and body_text is None:
            body_text = _part_text(part)
        elif part.get_content_type() == "text/html" and body_html is None:
            body_html = _part_text(part)

    return body_text, body_html, attachments


def read_attachment(
    raw: bytes, ref: AttachmentRef
) -> tuple[AttachmentInfo, bytes] | None:
    parts = [part for part in _leaf_parts(_parse_mime(raw)) if _is_attachment(part)]
    if not 0 <= ref.index < len(parts):
        return None
    part = parts[ref.index]
    return _attachment_info(ref.message, ref.index, part), _part_bytes(part)
