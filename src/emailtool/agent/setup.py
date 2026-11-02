from pydantic_ai import Agent
from pydantic_ai.models import infer_model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers import infer_provider_class
from pydantic_ai.providers.openai import OpenAIProvider


def build_agent(llm: str, token: str, base_url: str | None = None) -> Agent:
    if base_url:
        provider = OpenAIProvider(base_url=base_url, api_key=token)
        return Agent(OpenAIChatModel(llm, provider=provider))

    model = infer_model(
        llm,
        provider_factory=lambda provider: infer_provider_class(provider)(api_key=token),  # pyright: ignore[reportCallIssue]
    )
    return Agent(model)
