import pytest

from smart_commit import LazyCommitError
from smart_commit.git import GitRepo, parse_status

from .conftest import git, write


def test_parse_status_entries():
    output = "\0".join(
        [
            "# branch.oid abc",
            "# branch.head main",
            "# branch.upstream origin/main",
            "1 .M N... 100644 100644 100644 a a lib/core.py",
            "1 A. N... 000000 100644 100644 0 b with space.txt",
            "2 R. N... 100644 100644 100644 a a R100 new.py",
            "old.py",
            "u UU N... 100644 100644 100644 100644 a b c conflict.py",
            "? 中文.md",
            "",
        ]
    )
    status = parse_status(output)

    assert (status.branch, status.upstream, status.has_commits) == ("main", "origin/main", True)
    paths = [(c.path, c.index, c.worktree, c.orig_path) for c in status.changes]
    assert paths == [
        ("lib/core.py", ".", "M", None),
        ("with space.txt", "A", ".", None),
        ("new.py", "R", ".", "old.py"),
        ("conflict.py", "U", "U", None),
        ("中文.md", "?", "?", None),
    ]
    assert [c.path for c in status.staged] == ["with space.txt", "new.py"]
    assert [c.path for c in status.conflicts] == ["conflict.py"]


def test_parse_status_initial_and_detached():
    status = parse_status("# branch.oid (initial)\0# branch.head (detached)\0")
    assert status.has_commits is False
    assert status.branch is None


def test_status_codes_relative_to_head():
    status = parse_status(
        "1 AM N... 0 1 1 0 0 added.py\0"
        "1 MD N... 1 1 0 0 0 deleted.py\0"
        "1 D. N... 1 0 0 0 0 removed.py\0"
        "? new.py\0"
    )
    assert [c.status_code for c in status.changes] == ["A", "D", "D", "A"]


def test_status_with_unusual_paths(repo):
    for path in ["docs/中文说明.md", "my file.txt", "app/[slug]/page.tsx"]:
        write(repo.root, path, "x\n")

    status = repo.status()

    assert sorted(c.path for c in status.changes) == [
        "app/[slug]/page.tsx",
        "docs/中文说明.md",
        "my file.txt",
    ]
    assert all(c.untracked for c in status.changes)


def test_status_in_empty_repo(empty_repo):
    write(empty_repo.root, "a.py", "a\n")
    status = empty_repo.status()
    assert status.has_commits is False
    assert status.branch == "main"


def test_discover_outside_repo(tmp_path):
    with pytest.raises(LazyCommitError, match="Not inside a git work tree"):
        GitRepo.discover(tmp_path)


def test_discover_from_subdirectory(repo):
    sub = repo.root / "a" / "b"
    sub.mkdir(parents=True)
    assert GitRepo.discover(sub).root.resolve() == repo.root.resolve()


def test_diff_ignores_user_diff_config(repo):
    git(repo.root, "config", "color.ui", "always")
    git(repo.root, "config", "diff.noprefix", "true")
    git(repo.root, "config", "diff.mnemonicPrefix", "true")
    write(repo.root, "README.md", "changed\n")

    diff = repo.diff(repo.status(), staged_only=False)

    assert "\x1b[" not in diff
    assert diff.startswith("diff --git a/README.md b/README.md\n")


def test_diff_of_non_utf8_content(repo):
    write(repo.root, "gbk.py", "# 中文\n".encode("gbk"))
    git(repo.root, "add", ".")
    git(repo.root, "commit", "-qm", "add gbk")
    write(repo.root, "gbk.py", '# 中文\nx = "中"\n'.encode("gbk"))

    diff = repo.diff(repo.status(), staged_only=False)

    assert "+x = " in diff
