import os
import subprocess
from pathlib import Path

import pytest

from smart_commit.git import GitRepo
from smart_commit.models import CommitMessage, LLMInput
from smart_commit.settings import SmartCommitSettings


@pytest.fixture(autouse=True)
def isolated_env(tmp_path_factory, monkeypatch):
    """Keep the developer's git config, hooks and LAZY_COMMIT_* variables out of the tests."""
    home = tmp_path_factory.mktemp("home")
    gitconfig = home / ".gitconfig"
    gitconfig.write_text(
        "[user]\n\tname = Test\n\temail = test@example.com\n"
        "[init]\n\tdefaultBranch = main\n"
        "[commit]\n\tgpgsign = false\n"
    )
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(gitconfig))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for key in list(os.environ):
        if key.startswith("LAZY_COMMIT_"):
            monkeypatch.delenv(key)


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "core.quotePath=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def write(root: Path, path: str, content: str | bytes) -> None:
    full = root / path
    full.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        full.write_bytes(content)
    else:
        full.write_text(content, encoding="utf-8", newline="")


@pytest.fixture
def empty_repo(tmp_path) -> GitRepo:
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    return GitRepo(root)


@pytest.fixture
def repo(empty_repo) -> GitRepo:
    write(empty_repo.root, "README.md", "init\n")
    git(empty_repo.root, "add", ".")
    git(empty_repo.root, "commit", "-qm", "chore: init")
    return empty_repo


class FakeLLM:
    def __init__(self, message: CommitMessage | None = None, error: Exception | None = None):
        self.message = message or CommitMessage(type="feat", scope="core", title="add things")
        self.error = error
        self.inputs: list[LLMInput] = []

    def generate(self, llm_input: LLMInput) -> CommitMessage:
        self.inputs.append(llm_input)
        if self.error:
            raise self.error
        return self.message

    @property
    def diff(self) -> str:
        return self.inputs[-1].diff_content


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def settings() -> SmartCommitSettings:
    return SmartCommitSettings(_env_file=None)


@pytest.fixture(autouse=True)
def no_clipboard(monkeypatch):
    copied = []
    monkeypatch.setattr("pyperclip.copy", copied.append)
    return copied
