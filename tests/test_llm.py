from types import SimpleNamespace

import httpx2
import openai
import pytest

from smart_commit._tun import _is_lan_endpoint
from smart_commit import LazyCommitError
from smart_commit.llm import CommitMessageGenerator, build_messages, parse_commit_json
from smart_commit.models import CommitMessage, LLMInput
from smart_commit.settings import SmartCommitSettings


def bad_request(message: str) -> openai.BadRequestError:
    response = httpx2.Response(400, request=httpx2.Request("POST", "http://test/v1"))
    return openai.BadRequestError(message, response=response, body=None)


class FakeCompletions:
    """Stands in for client.chat.completions; `behaviour` maps call kinds to results."""

    def __init__(self, parse=None, json_object=None, plain=None):
        self.behaviour = {"parse": parse, "json_object": json_object, "plain": plain}
        self.calls = []

    def _respond(self, kind, kwargs):
        self.calls.append((kind, kwargs))
        result = self.behaviour[kind]
        if isinstance(result, Exception):
            raise result
        return result

    def parse(self, **kwargs):
        return self._respond("parse", kwargs)

    def create(self, **kwargs):
        kind = "json_object" if "response_format" in kwargs else "plain"
        return self._respond(kind, kwargs)


def completion(content=None, parsed=None):
    message = SimpleNamespace(content=content, parsed=parsed, refusal=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def generator(completions, **settings) -> CommitMessageGenerator:
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return CommitMessageGenerator(SmartCommitSettings(_env_file=None, **settings), client=client)


LLM_INPUT = LLMInput(
    git_branch_name="main",
    diff_content="diff --git a/x b/x",
    diff_source="staged changes",
    language="English",
    excluded_files=["uv.lock (+2 -1)"],
    recent_commits=["fix(api): handle timeouts"],
    hint="closes #3",
)
EXPECTED = CommitMessage(type="feat", scope="x", title="add x")
JSON = '{"type": "feat", "scope": "x", "title": "add x", "body": null}'


def test_structured_output():
    completions = FakeCompletions(parse=completion(parsed=EXPECTED))
    assert generator(completions).generate(LLM_INPUT) == EXPECTED
    assert "temperature" not in completions.calls[0][1]


def test_falls_back_to_json_mode_then_plain_text():
    completions = FakeCompletions(
        parse=bad_request("response_format json_schema is not supported"),
        json_object=bad_request("response_format is not supported"),
        plain=completion(content=f"<think>hmm</think>\n```json\n{JSON}\n```"),
    )

    assert generator(completions).generate(LLM_INPUT) == EXPECTED
    assert [kind for kind, _ in completions.calls] == ["parse", "json_object", "plain"]


def test_api_errors_become_user_errors():
    completions = FakeCompletions(
        parse=openai.APIConnectionError(request=httpx2.Request("POST", "http://x"))
    )
    with pytest.raises(LazyCommitError, match="LLM request failed"):
        generator(completions).generate(LLM_INPUT)


def test_extra_body_only_for_compatible_servers():
    official = FakeCompletions(parse=completion(parsed=EXPECTED))
    generator(official).generate(LLM_INPUT)
    assert "extra_body" not in official.calls[0][1]

    local = FakeCompletions(parse=completion(parsed=EXPECTED))
    generator(local, LAZY_COMMIT_OPENAI_BASE_URL="http://10.0.0.2/v1").generate(LLM_INPUT)
    assert local.calls[0][1]["extra_body"]["enable_thinking"] is False


def test_timeout_is_configurable():
    completions = FakeCompletions(parse=completion(parsed=EXPECTED))
    generator(completions).generate(LLM_INPUT)
    generator(completions, LAZY_COMMIT_TIMEOUT=300).generate(LLM_INPUT)
    assert [kwargs["timeout"] for _, kwargs in completions.calls] == [120, 300]


def test_client_retries_once():
    settings = SmartCommitSettings(_env_file=None, LAZY_COMMIT_OPENAI_API_KEY="sk-test")
    assert CommitMessageGenerator(settings).client.max_retries == 1


def test_missing_api_key_for_openai_is_reported():
    gen = CommitMessageGenerator(SmartCommitSettings(_env_file=None))
    with pytest.raises(LazyCommitError, match="LAZY_COMMIT_OPENAI_API_KEY is not set"):
        gen.generate(LLM_INPUT)


def test_prompt_contains_context_sections():
    user_prompt = build_messages(LLM_INPUT)[1]["content"]
    assert "- fix(api): handle timeouts" in user_prompt
    assert "- uv.lock (+2 -1)" in user_prompt
    assert "closes #3" in user_prompt
    assert "Changes to Commit (staged changes)" in user_prompt


def test_prompt_survives_braces_and_surrogates():
    llm_input = LLM_INPUT.model_copy(update={"diff_content": "+x = {'a': 1}\n+name \udcff"})
    user_prompt = build_messages(llm_input)[1]["content"]
    assert "{'a': 1}" in user_prompt
    user_prompt.encode("utf-8")


@pytest.mark.parametrize("text", ["no json here", '{"type": "feat"}'])
def test_parse_commit_json_errors(text):
    with pytest.raises(LazyCommitError):
        parse_commit_json(text)


def test_commit_message_normalization():
    message = CommitMessage(type=" Feat ", scope="", title="add x", body="  ")
    assert message.to_git_message() == "feat: add x"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://10.1.2.3:8000/v1", True),
        ("http://172.20.0.1/v1", True),
        ("http://192.168.1.10/v1", True),
        ("http://127.0.0.1:11434/v1", True),
        ("http://localhost:11434/v1", True),
        ("http://100.101.102.103/v1", True),  # Tailscale
        ("http://[fd00::1]/v1", True),
        ("http://172.32.0.1/v1", False),
        ("https://10.example.com/v1", False),
        ("https://api.openai.com/v1", False),
    ],
)
def test_is_lan_endpoint(url, expected):
    assert _is_lan_endpoint(url) is expected


def test_lan_client_only_when_bypass_enabled():
    from smart_commit._tun import get_lan_http_client

    assert get_lan_http_client("http://10.0.0.2/v1", bypass_proxy=False) is None
    assert get_lan_http_client("https://api.example.com/v1", bypass_proxy=True) is None
    client = get_lan_http_client("http://10.0.0.2/v1", bypass_proxy=True, timeout=httpx2.Timeout(5))
    assert client.trust_env is False
    assert client.timeout.connect == 5
