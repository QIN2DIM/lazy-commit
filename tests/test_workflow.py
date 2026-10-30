import pytest

from smart_commit import LazyCommitError
from smart_commit.git_commit_generator import GitCommitGenerator

from .conftest import git, write


def make(repo, settings, llm, **kwargs) -> GitCommitGenerator:
    return GitCommitGenerator(repo, settings, llm, **kwargs)


def head_files(repo) -> set[str]:
    return set(git(repo.root, "show", "--name-only", "--format=", "HEAD").split("\n")) - {""}


def staged(repo) -> list[str]:
    return sorted(c.path for c in repo.status().staged)


def test_generate_only_leaves_index_alone(repo, settings, llm, no_clipboard):
    write(repo.root, "app.py", "print(1)\n")

    message = make(repo, settings, llm).run()

    assert no_clipboard == [message.to_git_message()]
    assert staged(repo) == []
    assert "+print(1)" in llm.diff
    assert llm.inputs[0].recent_commits == ["chore: init"]


def test_no_changes(repo, settings, llm):
    assert make(repo, settings, llm, auto_add=True).run() is None
    assert llm.inputs == []


def test_add_stages_everything_including_unusual_paths(repo, settings, llm):
    paths = ["docs/中文说明.md", "my file.txt", "app/[slug]/page.tsx"]
    for path in paths:
        write(repo.root, path, "x\n")
    git(repo.root, "add", ".")
    git(repo.root, "commit", "-qm", "add")
    for path in paths:
        write(repo.root, path, "x\nmore\n")
    (repo.root / "README.md").unlink()

    make(repo, settings, llm, auto_add=True).run()

    assert head_files(repo) == {*paths, "README.md"}
    assert repo.status().changes == []
    for path in paths:
        assert f"diff --git a/{path} b/{path}" in llm.diff


def test_default_uses_latest_content_of_all_files(repo, settings, llm):
    # e.g. an IDE staged a new file when it was created, then it was edited further
    write(repo.root, "AGENTS.md", "v1\n")
    git(repo.root, "add", "AGENTS.md")
    write(repo.root, "AGENTS.md", "v2\n")
    write(repo.root, "other.py", "o\n")

    make(repo, settings, llm).run()

    assert "+v2" in llm.diff and "+v1" not in llm.diff
    assert "+o" in llm.diff


def test_add_stages_and_commits_everything(repo, settings, llm):
    write(repo.root, "staged.py", "s\n")
    git(repo.root, "add", "staged.py")
    write(repo.root, "staged.py", "s2\n")
    write(repo.root, "unstaged.py", "u\n")

    make(repo, settings, llm, auto_add=True).run()

    assert head_files(repo) == {"staged.py", "unstaged.py"}
    assert git(repo.root, "show", "HEAD:staged.py") == "s2\n"
    assert repo.status().changes == []


def test_staged_only_commits_just_the_index(repo, settings, llm):
    write(repo.root, "staged.py", "s\n")
    write(repo.root, "unstaged.py", "u\n")
    git(repo.root, "add", "staged.py")

    make(repo, settings, llm, auto_add=True, staged_only=True).run()

    assert head_files(repo) == {"staged.py"}
    assert [c.path for c in repo.status().changes] == ["unstaged.py"]
    assert "unstaged.py" not in llm.diff
    assert "git diff --cached" in llm.inputs[0].diff_source


def test_staged_only_with_nothing_staged(repo, settings, llm):
    write(repo.root, "unstaged.py", "u\n")

    assert make(repo, settings, llm, auto_add=True, staged_only=True).run() is None
    assert llm.inputs == []


def test_llm_failure_restores_index(repo, settings):
    write(repo.root, "partial.py", "p\n")
    write(repo.root, "other.py", "o\n")
    git(repo.root, "add", "partial.py")
    llm = type(
        "Failing", (), {"generate": lambda self, _: (_ for _ in ()).throw(LazyCommitError("boom"))}
    )()

    with pytest.raises(LazyCommitError, match="boom"):
        make(repo, settings, llm, auto_add=True).run()

    assert staged(repo) == ["partial.py"]
    assert git(repo.root, "rev-list", "--count", "HEAD").strip() == "1"


def test_hook_failure_raises_and_restores_index(repo, settings, llm):
    hook = repo.root / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho 'lint failed [/E501]' >&2\nexit 1\n", newline="")
    hook.chmod(0o755)
    write(repo.root, "app.py", "x\n")

    with pytest.raises(LazyCommitError, match=r"lint failed \[/E501\]"):
        make(repo, settings, llm, auto_add=True).run()

    assert staged(repo) == []
    assert git(repo.root, "rev-list", "--count", "HEAD").strip() == "1"


def test_first_commit_in_empty_repo(empty_repo, settings, llm):
    write(empty_repo.root, "main.py", "print('hi')\n")

    make(empty_repo, settings, llm, auto_add=True).run()

    assert head_files(empty_repo) == {"main.py"}
    assert llm.inputs[0].recent_commits == []


def test_generate_only_in_empty_repo(empty_repo, settings, llm):
    write(empty_repo.root, "a.py", "a\n")
    write(empty_repo.root, "b.py", "b\n")
    git(empty_repo.root, "add", "a.py")

    make(empty_repo, settings, llm).run()

    assert "+a" in llm.diff and "+b" in llm.diff


def test_lock_only_change_can_be_committed(repo, settings, llm):
    write(repo.root, "uv.lock", "v1\n")
    git(repo.root, "add", ".")
    git(repo.root, "commit", "-qm", "lock")
    write(repo.root, "uv.lock", "v2\nv3\n")

    make(repo, settings, llm, auto_add=True).run()

    assert head_files(repo) == {"uv.lock"}
    assert llm.inputs[0].excluded_files == ["uv.lock (+2 -1)"]
    assert "only lock or generated files" in llm.diff


def test_binary_untracked_file_is_not_dumped(repo, settings, llm):
    write(repo.root, "logo.png", b"\x89PNG\0\0garbage" * 100)

    make(repo, settings, llm).run()

    assert "garbage" not in llm.diff
    assert "Binary file" in llm.diff


def test_merge_conflicts_abort(repo, settings, llm):
    write(repo.root, "f.txt", "base\n")
    git(repo.root, "add", ".")
    git(repo.root, "commit", "-qm", "base")
    git(repo.root, "checkout", "-qb", "other")
    write(repo.root, "f.txt", "other\n")
    git(repo.root, "commit", "-qam", "other")
    git(repo.root, "checkout", "-q", "main")
    write(repo.root, "f.txt", "main\n")
    git(repo.root, "commit", "-qam", "main")
    with pytest.raises(Exception):
        git(repo.root, "merge", "other")

    with pytest.raises(LazyCommitError, match="merge conflicts"):
        make(repo, settings, llm, auto_add=True).run()


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(path))
    return path


def test_push_sets_upstream_when_missing(repo, settings, llm, remote):
    git(repo.root, "remote", "add", "origin", str(remote))
    write(repo.root, "app.py", "x\n")

    make(repo, settings, llm, auto_push=True).run()

    assert git(remote, "log", "--format=%s", "main").startswith("feat(core): add things")
    assert git(repo.root, "rev-parse", "--abbrev-ref", "@{upstream}").strip() == "origin/main"


def test_push_uses_existing_upstream(repo, settings, llm, remote):
    git(repo.root, "remote", "add", "backup", str(remote))
    git(repo.root, "push", "-qu", "backup", "main")
    write(repo.root, "app.py", "x\n")

    make(repo, settings, llm, auto_push=True).run()

    assert git(remote, "log", "-1", "--format=%s", "main").startswith("feat(core)")


def test_push_failure_keeps_commit_and_reports_it(repo, settings, llm):
    write(repo.root, "app.py", "x\n")

    with pytest.raises(LazyCommitError, match="commit was created, but pushing failed"):
        make(repo, settings, llm, auto_push=True).run()

    assert head_files(repo) == {"app.py"}


def test_print_only_writes_message_to_stdout(repo, settings, llm, capsys, no_clipboard):
    write(repo.root, "app.py", "x\n")

    make(repo, settings, llm, print_only=True).run()

    assert capsys.readouterr().out == "feat(core): add things\n"
    assert no_clipboard == []


def test_hint_and_language_are_passed_to_llm(repo, settings, llm):
    write(repo.root, "app.py", "x\n")

    make(repo, settings, llm, hint="fixes #12", language="简体中文").run()

    assert llm.inputs[0].hint == "fixes #12"
    assert llm.inputs[0].language == "简体中文"


def test_extra_exclude_patterns(repo, llm):
    from smart_commit.settings import SmartCommitSettings

    settings = SmartCommitSettings(_env_file=None, LAZY_COMMIT_EXCLUDE_PATTERNS="*.snap, gen/*")
    write(repo.root, "tests/a.snap", "s\n")
    write(repo.root, "gen/api.py", "g\n")
    write(repo.root, "app.py", "x\n")

    make(repo, settings, llm).run()

    assert sorted(e.split(" ")[0] for e in llm.inputs[0].excluded_files) == [
        "gen/api.py",
        "tests/a.snap",
    ]
