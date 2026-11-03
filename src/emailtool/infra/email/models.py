from datetime import date, datetime

from pydantic import BaseModel, Field


class MessageFilter(BaseModel):
    sender: str | None = None
    recipient: str | None = None  # Matches To or Cc
    subject: str | None = None
    body: str | None = None
    since: date | None = None
    before: date | None = None
    unread_only: bool = False
    has_attachments: bool = False
    folder: str = "INBOX"
    limit: int = Field(default=50, gt=0)


class AttachmentInfo(BaseModel):
    filename: str
    content_type: str
    size: int


class AttachmentContent(AttachmentInfo):
    data: bytes


class MessageSummary(BaseModel):
    message_id: str | None  # The Message-ID header, used to open threads
    sender: str | None
    to: list[str]
    cc: list[str]
    subject: str
    date: datetime
    is_read: bool
    has_attachments: bool


class EmailMessage(MessageSummary):
    body_text: str | None
    body_html: str | None
    attachments: list[AttachmentInfo]


class EmailThread(BaseModel):
    messages: list[EmailMessage]  # Oldest first
