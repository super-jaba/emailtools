import asyncio
import secrets
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession

from emailtool.agent import build_agent
from emailtool.config import settings
from emailtool.infra.email import ImapMailbox, MailboxError, MessageFilter

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage

    from emailtool.infra.email import Mailbox

DEV_DOMAIN = "emailtool.local"


def build_mailbox() -> ImapMailbox:
    address = settings.EMAIL_ADDRESS or f"{secrets.token_hex(4)}@{DEV_DOMAIN}"
    password = (
        settings.EMAIL_PASSWORD.get_secret_value()
        if settings.EMAIL_PASSWORD
        else address
    )
    return ImapMailbox(
        address, password, settings.IMAP_HOST, settings.IMAP_PORT, settings.IMAP_SSL
    )


async def conversation(agent: Agent[Mailbox], mailbox: Mailbox) -> None:
    try:
        # Fails fast when the server is down; GreenMail also creates the user here.
        await mailbox.list_messages(MessageFilter(limit=1))
    except MailboxError as e:
        print(f"Mail server unreachable ({e}). Is it running? Try `make mail-up`.")
        return

    print(f"Session address: {mailbox.address}")
    print(f"Send mail with: make send-mail TO={mailbox.address}\n")

    session: PromptSession[str] = PromptSession()
    history: list[ModelMessage] = []

    while True:
        try:
            prompt = (await session.prompt_async("you> ")).strip()
        except EOFError, KeyboardInterrupt:
            break

        if not prompt:
            continue
        if prompt in ("/exit", "/quit", "/q"):
            break

        async with agent.run_stream(
            prompt, message_history=history, deps=mailbox
        ) as result:
            async for chunk in result.stream_text(delta=True):
                print(chunk, end="", flush=True)
        history = result.all_messages()
        print()


def main() -> None:
    agent = build_agent(
        settings.LLM_MODEL,
        settings.LLM_TOKEN.get_secret_value(),
        settings.LLM_BASE_URL,
    )
    asyncio.run(conversation(agent, build_mailbox()))


if __name__ == "__main__":
    main()
