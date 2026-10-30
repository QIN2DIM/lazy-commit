# -*- coding: utf-8 -*-
"""
@Desc    : Ask an OpenAI-compatible model for a structured commit message.
"""

import re

import openai
from openai import OpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from pydantic import ValidationError

from smart_commit import LazyCommitError
from smart_commit._tun import get_lan_http_client
from smart_commit.models import CommitMessage, LLMInput
from smart_commit.prompts import (
    EXCLUDED_FILES_SECTION,
    HINT_SECTION,
    RECENT_COMMITS_SECTION,
    SYSTEM_INSTRUCTIONS_TEMPLATE,
    USER_PROMPT_TEMPLATE,
)
from smart_commit.settings import SmartCommitSettings

# Switches off "thinking" on Qwen3-style servers (vLLM, SiliconFlow, ModelScope...).
# Not sent to the official OpenAI API, which rejects unknown request arguments.
_DISABLE_THINKING = {
    "chat_template_kwargs": {"enable_thinking": False, "thinking": False},
    "enable_thinking": False,
    "thinking": False,
}

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def build_messages(llm_input: LLMInput) -> list[ChatCompletionMessageParam]:
    sections = []
    if llm_input.recent_commits:
        commits = "\n".join(f"- {subject}" for subject in llm_input.recent_commits)
        sections.append(RECENT_COMMITS_SECTION.format(commits=commits))
    if llm_input.excluded_files:
        files = "\n".join(f"- {entry}" for entry in llm_input.excluded_files)
        sections.append(EXCLUDED_FILES_SECTION.format(files=files))
    if llm_input.hint:
        sections.append(HINT_SECTION.format(hint=llm_input.hint))

    user_prompt = USER_PROMPT_TEMPLATE.format(
        branch_name=llm_input.git_branch_name,
        extra_sections="".join(sections),
        diff_source=llm_input.diff_source,
        diff_content=llm_input.diff_content,
        language=llm_input.language,
    )
    system_prompt = SYSTEM_INSTRUCTIONS_TEMPLATE.format(language=llm_input.language)
    return [
        ChatCompletionSystemMessageParam(role="system", content=system_prompt),
        # Lone surrogates (from non-UTF-8 file names) can't be JSON-encoded for the request
        ChatCompletionUserMessageParam(
            role="user", content=user_prompt.encode("utf-8", "replace").decode("utf-8")
        ),
    ]


def parse_commit_json(text: str) -> CommitMessage:
    """Extract a CommitMessage from free-form model output (code fences, <think> blocks...)."""
    text = _THINK_BLOCK.sub("", text)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise LazyCommitError(f"The model did not return a JSON object: {text[:200]!r}")
    try:
        return CommitMessage.model_validate_json(text[start : end + 1])
    except ValidationError as e:
        raise LazyCommitError(f"The model returned an invalid commit message:\n{e}") from e


class CommitMessageGenerator:
    """Generates commit messages, degrading gracefully on servers without structured outputs."""

    def __init__(self, settings: SmartCommitSettings, client: OpenAI | None = None):
        self._settings = settings
        self._model = settings.LAZY_COMMIT_OPENAI_MODEL_NAME
        self._client = client

    @property
    def client(self) -> OpenAI:
        # Created lazily so a missing API key isn't reported when there is nothing to commit
        if self._client is None:
            self._client = self._create_client()
        return self._client

    def _create_client(self) -> OpenAI:
        settings = self._settings
        if not settings.LAZY_COMMIT_OPENAI_API_KEY:
            raise LazyCommitError(
                "LAZY_COMMIT_OPENAI_API_KEY is not set. Export it or add it to .env (see README)."
            )
        base_url = settings.LAZY_COMMIT_OPENAI_BASE_URL
        return OpenAI(
            api_key=settings.LAZY_COMMIT_OPENAI_API_KEY.get_secret_value(),
            base_url=base_url,
            http_client=(
                get_lan_http_client(base_url, bypass_proxy=settings.LAZY_COMMIT_BYPASS_PROXY)
                if base_url
                else None
            ),
            # A retry starts the generation over; the SDK default (2) can triple a timeout
            max_retries=1,
        )

    def _request_options(self) -> dict:
        # No temperature: reasoning models reject anything but their default
        options = {"model": self._model, "timeout": self._settings.LAZY_COMMIT_TIMEOUT}
        if not self._settings.is_official_openai:
            options["extra_body"] = _DISABLE_THINKING
        return options

    def generate(self, llm_input: LLMInput) -> CommitMessage:
        messages = build_messages(llm_input)
        try:
            try:
                return self._generate_structured(messages)
            except openai.BadRequestError:
                # Many OpenAI-compatible servers reject `json_schema` response formats:
                # retry with JSON mode, then with no response format at all.
                pass
            try:
                return self._generate_json(messages, {"type": "json_object"})
            except openai.BadRequestError:
                return self._generate_json(messages, None)
        except openai.OpenAIError as e:  # API errors, timeouts, truncated output...
            raise LazyCommitError(f"LLM request failed: {e}") from e

    def _generate_structured(self, messages: list[ChatCompletionMessageParam]) -> CommitMessage:
        completion = self.client.chat.completions.parse(
            messages=messages, response_format=CommitMessage, **self._request_options()
        )
        message = completion.choices[0].message
        if message.parsed is None:
            raise LazyCommitError(f"The model refused to answer: {message.refusal or 'no reason'}")
        return message.parsed

    def _generate_json(
        self, messages: list[ChatCompletionMessageParam], response_format: dict | None
    ) -> CommitMessage:
        options = self._request_options()
        if response_format is not None:
            options["response_format"] = response_format
        completion = self.client.chat.completions.create(messages=messages, **options)
        return parse_commit_json(completion.choices[0].message.content or "")
