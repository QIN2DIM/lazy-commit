import os

import pytest
from typer.testing import CliRunner

from smart_commit import cli

from .conftest import FakeLLM, write


@pytest.fixture
def fake_llm(monkeypatch):
    llm = FakeLLM()
    monkeypatch.setattr(cli, "CommitMessageGenerator", lambda settings: llm)
    return llm


def invoke(monkeypatch, cwd, *args):
    monkeypatch.chdir(cwd)
    return CliRunner().invoke(cli.app, list(args))


def test_not_a_repo_is_a_clean_error(monkeypatch, tmp_path):
    result = invoke(monkeypatch, tmp_path)
    assert result.exit_code == 1
    assert "Not inside a git work tree" in result.output
    assert "Traceback" not in result.output


def test_print_mode(monkeypatch, repo, fake_llm):
    write(repo.root, "app.py", "x\n")
    result = invoke(monkeypatch, repo.root, "--print")
    assert result.exit_code == 0
    assert result.stdout == "feat(core): add things\n"


def test_print_conflicts_with_add(monkeypatch, repo, fake_llm):
    result = invoke(monkeypatch, repo.root, "--print", "--add")
    assert result.exit_code == 2


def test_failure_exit_code(monkeypatch, repo, fake_llm):
    write(repo.root, "app.py", "x\n")
    result = invoke(monkeypatch, repo.root, "--push")  # no remote configured
    assert result.exit_code == 1
    assert "commit was created, but pushing failed" in result.output


def test_project_env_overrides_exported_variables(monkeypatch, repo, fake_llm):
    write(repo.root, ".env", "LAZY_COMMIT_LANGUAGE=日本語\nAPP_SECRET=not-for-git-hooks\n")
    write(repo.root, "pkg/app.py", "x\n")
    monkeypatch.setenv("LAZY_COMMIT_LANGUAGE", "English")
    monkeypatch.delenv("APP_SECRET", raising=False)

    result = invoke(monkeypatch, repo.root / "pkg")

    assert result.exit_code == 0
    assert fake_llm.inputs[0].language == "日本語"
    assert "APP_SECRET" not in os.environ


def test_paths_are_not_parsed_as_markup(monkeypatch, repo, fake_llm):
    write(repo.root, "app/[slug]/page.tsx", "x\n")
    result = invoke(monkeypatch, repo.root)
    assert "app/[slug]/page.tsx" in result.output


def test_version(monkeypatch, tmp_path):
    result = invoke(monkeypatch, tmp_path, "--version")
    assert result.exit_code == 0
    assert result.output.startswith("lazy-commit ")
