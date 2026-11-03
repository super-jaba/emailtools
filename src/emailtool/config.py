from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    LLM_MODEL: str  # "<provider>:<model>", e.g. "anthropic:claude-opus-5-5"
    LLM_TOKEN: SecretStr
    # Set for OpenAI-compatible gateways (e.g. https://openrouter.ai/api/v1);
    # LLM_MODEL is then the plain gateway slug, without a "<provider>:" prefix.
    LLM_BASE_URL: str | None = None

    IMAP_HOST: str = "localhost"
    IMAP_PORT: int = 3143
    IMAP_SSL: bool = False
    # Unset: a random dev address is generated on every start.
    EMAIL_ADDRESS: str | None = None
    # Unset: the address doubles as the password, which GreenMail accepts.
    EMAIL_PASSWORD: SecretStr | None = None


settings = Settings()  # pyright: ignore[reportCallIssue]
