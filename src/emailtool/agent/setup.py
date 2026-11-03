from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model, infer_model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers import infer_provider_class
from pydantic_ai.providers.openai import OpenAIProvider

from emailtool.agent.tools import mailbox_toolset
from emailtool.infra.email import Mailbox


def _instructions(ctx: RunContext[Mailbox]) -> str:
    return (
        f"You are an email assistant for the address {ctx.deps.address}. "
        "The user forwards emails there for you to process. Use the tools to "
        "find and read messages instead of guessing what they contain. "
        "Forwarded mail usually carries the original message inside its body."
    )


def _agent(model: Model) -> Agent[Mailbox]:
    return Agent(
        model,
        deps_type=Mailbox,
        toolsets=[mailbox_toolset],
        instructions=_instructions,
    )


def build_agent(llm: str, token: str, base_url: str | None = None) -> Agent[Mailbox]:
    if base_url:
        provider = OpenAIProvider(base_url=base_url, api_key=token)
        return _agent(OpenAIChatModel(llm, provider=provider))

    model = infer_model(
        llm,
        provider_factory=lambda provider: infer_provider_class(provider)(api_key=token),  # pyright: ignore[reportCallIssue]
    )
    return _agent(model)
