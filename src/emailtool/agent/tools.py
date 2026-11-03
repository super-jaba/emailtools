from datetime import date
from typing import Annotated

from pydantic import Field
from pydantic_ai import BinaryContent, FunctionToolset, ModelRetry, RunContext

from emailtool.infra.email import (
    AttachmentNotFound,
    EmailThread,
    Mailbox,
    MailboxError,
    MessageFilter,
    MessageNotFound,
    MessageSummary,
)

TEXT_TYPES = ("application/json", "application/xml", "application/csv")

mailbox_toolset: FunctionToolset[Mailbox] = FunctionToolset()


@mailbox_toolset.tool
async def list_messages(
    ctx: RunContext[Mailbox],
    sender: str | None = None,
    subject: str | None = None,
    body: str | None = None,
    since: date | None = None,
    before: date | None = None,
    unread_only: bool = False,
    has_attachments: bool = False,
    limit: Annotated[int, Field(gt=0)] = 20,
) -> list[MessageSummary] | str:
    """List messages in the session inbox, newest first.

    Args:
        sender: Substring of the sender's name or address.
        subject: Text the subject contains.
        body: Text the body contains.
        since: Only messages on or after this date.
        before: Only messages before this date.
        unread_only: Only messages not read yet.
        has_attachments: Only messages with attachments.
        limit: Maximum number of messages to return.
    """
    filters = MessageFilter(
        sender=sender,
        subject=subject,
        body=body,
        since=since,
        before=before,
        unread_only=unread_only,
        has_attachments=has_attachments,
        limit=limit,
    )
    try:
        return await ctx.deps.list_messages(filters)
    except MailboxError as e:
        return f"Error: {e}"


@mailbox_toolset.tool
async def read_thread(ctx: RunContext[Mailbox], message_id: str) -> EmailThread | str:
    """Read the full thread a message belongs to, oldest message first.

    Args:
        message_id: The message_id of any message in the thread, from list_messages.
    """
    try:
        thread = await ctx.deps.get_thread(message_id)
    except MessageNotFound as e:
        raise ModelRetry(str(e)) from e
    except MailboxError as e:
        return f"Error: {e}"

    for message in thread.messages:
        if message.body_text:
            message.body_html = None
    return thread


@mailbox_toolset.tool
async def read_attachment(
    ctx: RunContext[Mailbox], message_id: str, filename: str
) -> BinaryContent | str:
    """Read the content of a message attachment.

    Text is returned as is; images and PDFs are returned for you to view.

    Args:
        message_id: The message_id of the message, from list_messages.
        filename: The attachment's filename, from read_thread.
    """
    try:
        attachment = await ctx.deps.get_attachment(message_id, filename)
    except (MessageNotFound, AttachmentNotFound) as e:
        raise ModelRetry(str(e)) from e
    except MailboxError as e:
        return f"Error: {e}"

    content_type = attachment.content_type.lower()
    if content_type.startswith("text/") or content_type in TEXT_TYPES:
        return attachment.data.decode("utf-8", errors="replace")
    if content_type.startswith("image/") or content_type == "application/pdf":
        return BinaryContent(attachment.data, media_type=content_type)
    return (
        f"Cannot read {attachment.filename}: unsupported type "
        f"{attachment.content_type} ({attachment.size} bytes)."
    )
