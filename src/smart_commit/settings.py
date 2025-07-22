from typing import Any

import dotenv
from pydantic import Field, SecretStr
from pydantic_settings import SettingsConfigDict, BaseSettings

dotenv.load_dotenv()


class SmartCommitSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    SMART_COMMIT_OPENAI_BASE_URL: str | None = Field(
        default=None, description="It only needs to be changed when calling the local model"
    )
    SMART_COMMIT_OPENAI_API_KEY: SecretStr | None = Field(
        default=None, description="When calling the local model, this value can be empty"
    )
    SMART_COMMIT_OPENAI_MODEL_NAME: str | None = Field(
        default=None, description="When calling the local model, this value can be empty"
    )
    SMART_COMMIT_MAX_CONTEXT_SIZE: int = Field(
        default=32000, description="Maximum context length (number of characters), 30k", gt=512
    )

    def model_post_init(self, context: Any, /) -> None:
        if not self.SMART_COMMIT_OPENAI_BASE_URL or self.SMART_COMMIT_OPENAI_BASE_URL in [
            "https://api.openai.com/v1"
        ]:
            if not self.SMART_COMMIT_OPENAI_MODEL_NAME:
                self.SMART_COMMIT_OPENAI_MODEL_NAME = "gpt-4.1-mini"

        if not self.SMART_COMMIT_OPENAI_API_KEY:
            self.SMART_COMMIT_OPENAI_API_KEY = SecretStr("local-model-api-key")
        if not self.SMART_COMMIT_OPENAI_MODEL_NAME:
            self.SMART_COMMIT_OPENAI_MODEL_NAME = "local-model"


settings = SmartCommitSettings()
