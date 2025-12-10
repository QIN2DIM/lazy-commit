from typing import Any

import dotenv
from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict, BaseSettings

dotenv.load_dotenv()


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
        default=32000, description="Maximum context length (number of characters), 30k", gt=512
    )
    LAZY_COMMIT_BYPASS_PROXY: bool = Field(
        default=False,
        description="""
        When set to True, LAN endpoints (private IP addresses like 10.x, 172.16-31.x, 192.168.x)
        will bypass system proxy and TUN mode (e.g., Clash-Meta). Useful when accessing internal
        model endpoints via VPN that would otherwise be intercepted by proxy software.
        """,
    )

    def model_post_init(self, context: Any, /) -> None:
        if not self.LAZY_COMMIT_OPENAI_BASE_URL or self.LAZY_COMMIT_OPENAI_BASE_URL in [
            "https://api.openai.com/v1"
        ]:
            if not self.LAZY_COMMIT_OPENAI_MODEL_NAME:
                self.LAZY_COMMIT_OPENAI_MODEL_NAME = "gpt-4.1-mini"

        if not self.LAZY_COMMIT_OPENAI_API_KEY:
            self.LAZY_COMMIT_OPENAI_API_KEY = SecretStr("local-model-api-key")
        if not self.LAZY_COMMIT_OPENAI_MODEL_NAME:
            self.LAZY_COMMIT_OPENAI_MODEL_NAME = "local-model"


settings = SmartCommitSettings()
