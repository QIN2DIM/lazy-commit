from typing import Any

import dotenv
from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict, BaseSettings

dotenv.load_dotenv()

OPENAI_BASE_URL = "https://api.openai.com/v1"


class SmartCommitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    LAZY_COMMIT_OPENAI_BASE_URL: str | None = Field(
        default=None,
        description="""
        It only needs to be changed when using alternative providers.
        Free models available at https://openrouter.ai/api/v1 (OpenRouter) or
        https://api.siliconflow.cn/v1 (SiliconFlow for Chinese users)
        """,
    )
    LAZY_COMMIT_OPENAI_API_KEY: SecretStr | None = Field(
        default=None, description="When calling the local model, this value can be empty"
    )
    LAZY_COMMIT_OPENAI_MODEL_NAME: str | None = Field(
        default=None, description="When calling the local model, this value can be empty"
    )
    LAZY_COMMIT_MAX_CONTEXT_SIZE: int = Field(
        default=32000, description="Token budget for the diff sent to the model", gt=512
    )
    LAZY_COMMIT_TIMEOUT: float = Field(
        default=120,
        description="""
        Timeout in seconds for one LLM request. Responses aren't streamed, so this bounds the
        whole generation: reasoning models and local models on large diffs need the headroom.
        """,
        gt=0,
    )
    LAZY_COMMIT_EXCLUDE_PATTERNS: str = Field(
        default="",
        description="""
        Extra comma-separated glob patterns to leave out of the analyzed diff, on top of
        the built-in lock file patterns, e.g. "*.snap,generated/*". Patterns without "/"
        match the file name in any directory.
        """,
    )
    LAZY_COMMIT_BYPASS_PROXY: bool = Field(
        default=False,
        description="""
        When set to True, LAN endpoints (private IP addresses like 10.x, 172.16-31.x, 192.168.x)
        will bypass system proxy and TUN mode (e.g., Clash-Meta). Useful when accessing internal
        model endpoints via VPN that would otherwise be intercepted by proxy software.
        """,
    )
    LAZY_COMMIT_LANGUAGE: str = Field(
        default="English",
        description="""
        The language used for generating commit messages.
        You can set it to any natural language like "English", "简体中文", "日本語", etc.
        The model will understand and generate commit messages in the specified language.
        """,
    )

    @property
    def is_official_openai(self) -> bool:
        return self.LAZY_COMMIT_OPENAI_BASE_URL in (None, OPENAI_BASE_URL)

    def model_post_init(self, context: Any, /) -> None:
        if self.is_official_openai:
            if not self.LAZY_COMMIT_OPENAI_MODEL_NAME:
                self.LAZY_COMMIT_OPENAI_MODEL_NAME = "gpt-4.1-mini"
            return

        if not self.LAZY_COMMIT_OPENAI_API_KEY:
            self.LAZY_COMMIT_OPENAI_API_KEY = SecretStr("local-model-api-key")
        if not self.LAZY_COMMIT_OPENAI_MODEL_NAME:
            self.LAZY_COMMIT_OPENAI_MODEL_NAME = "local-model"


settings = SmartCommitSettings()
