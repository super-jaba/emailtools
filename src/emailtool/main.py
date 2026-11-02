import asyncio
from typing import TYPE_CHECKING

from prompt_toolkit import PromptSession

from emailtool.agent import build_agent
from emailtool.config import settings

if TYPE_CHECKING:
    from pydantic_ai import Agent
    from pydantic_ai.messages import ModelMessage


async def conversation(agent: Agent) -> None:
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

        async with agent.run_stream(prompt, message_history=history) as result:
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
    asyncio.run(conversation(agent))


if __name__ == "__main__":
    main()
