from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from emailtool.infra.email.models import (
        AttachmentContent,
        EmailThread,
        MessageFilter,
        MessageSummary,
    )


class MailboxError(Exception):
    pass


class MessageNotFound(MailboxError):
    pass


class AttachmentNotFound(MailboxError):
    pass


class Mailbox(ABC):
    @property
    @abstractmethod
    def address(self) -> str: ...

    @abstractmethod
    async def list_messages(
        self, filters: MessageFilter | None = None
    ) -> list[MessageSummary]: ...

    @abstractmethod
    async def get_thread(self, message_id: str) -> EmailThread: ...

    @abstractmethod
    async def get_attachment(self, attachment_id: str) -> AttachmentContent: ...
