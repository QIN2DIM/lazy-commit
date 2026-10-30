import pytest

from smart_commit import diff as diff_module
from smart_commit.diff import (
    FileDiff,
    MAX_UNTRACKED_BYTES,
    collect_changes,
    count_tokens,
    fit_to_budget,
    is_excluded,
    split_diff,
    untracked_file_diff,
)

from .conftest import git, write


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("uv.lock", True),
        ("sub/yarn.lock", True),
        ("frontend/package-lock.json", True),
        ("apps/web/pnpm-lock.yaml", True),
        ("go.sum", True),
        ("dist/app.min.js", True),
        ("notebooks/demo.ipynb", True),
        ("src/lock.py", False),
        ("package.json", False),
    ],
)
def test_is_excluded(path, expected):
    assert is_excluded(path) is expected


def test_is_excluded_with_directory_pattern():
    assert is_excluded("generated/api.py", ("generated/*",))
    assert not is_excluded("src/generated/api.py", ("generated/*",))


def test_split_diff_paths():
    raw = (
        "diff --git a/lib/core.py b/lib/core.py\n"
        "index 1..2 100644\n--- a/lib/core.py\n+++ b/lib/core.py\n"
        "@@ -1 +1,2 @@\n x\n"
        # A line that merely contains a diff header must not start a new file
        '+s = f"diff --git a/{p} b/{p}"\n'
        "diff --git a/gone.py b/gone.py\n"
        "deleted file mode 100644\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-d\n"
        "diff --git a/old name.py b/new name.py\n"
        "similarity index 100%\nrename from old name.py\nrename to new name.py\n"
        "diff --git a/logo.png b/logo.png\n"
        "Binary files a/logo.png and b/logo.png differ\n"
        'diff --git "a/we\\"ird" "b/we\\"ird"\n'
        '--- "a/we\\"ird"\n+++ "b/we\\"ird"\n@@ -1 +1 @@\n-a\n+b\n'
    )

    files = split_diff(raw)

    assert [f.path for f in files] == [
        "lib/core.py",
        "gone.py",
        "new name.py",
        "logo.png",
        'we"ird',
    ]
    assert 'f"diff --git' in files[0].text
    assert files[0].stat == "+1 -0"
    assert files[1].stat == "+0 -1"


def test_untracked_text_file(tmp_path):
    write(tmp_path, "new.py", "a\nb\n")
    text = untracked_file_diff(tmp_path, "new.py").text
    assert text.endswith("@@ -0,0 +1,2 @@\n+a\n+b")


def test_untracked_binary_file(tmp_path):
    write(tmp_path, "logo.png", b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR" + bytes(range(256)))
    text = untracked_file_diff(tmp_path, "logo.png").text
    assert "Binary file added" in text
    assert "IHDR" not in text


def test_untracked_large_file_is_capped(tmp_path):
    write(tmp_path, "big.txt", "x" * 99 + "\n" * 1 + "y" * (MAX_UNTRACKED_BYTES * 2))
    text = untracked_file_diff(tmp_path, "big.txt").text
    assert len(text) < MAX_UNTRACKED_BYTES + 1000
    assert "file truncated" in text


def test_untracked_non_utf8_file(tmp_path):
    write(tmp_path, "gbk.txt", "中文".encode("gbk"))
    assert "+" in untracked_file_diff(tmp_path, "gbk.txt").text


def test_collect_changes_separates_lock_files(repo):
    write(repo.root, "app.py", "print(1)\n")
    write(repo.root, "web/package-lock.json", "{}\n")

    bundle = collect_changes(repo, repo.status(), staged_only=False)

    assert [f.path for f in bundle.files] == ["app.py"]
    assert [f.path for f in bundle.excluded] == ["web/package-lock.json"]


def test_collect_changes_staged_only(repo):
    write(repo.root, "staged.py", "s\n")
    write(repo.root, "unstaged.py", "u\n")
    git(repo.root, "add", "staged.py")

    bundle = collect_changes(repo, repo.status(), staged_only=True)

    assert [f.path for f in bundle.files] == ["staged.py"]


def test_collect_changes_detects_staged_rename(repo):
    write(repo.root, "old_name.py", "".join(f"line {i}\n" for i in range(50)))
    git(repo.root, "add", ".")
    git(repo.root, "commit", "-qm", "add")
    git(repo.root, "mv", "old_name.py", "new_name.py")

    bundle = collect_changes(repo, repo.status(), staged_only=True)

    assert [f.path for f in bundle.files] == ["new_name.py"]
    assert "rename from old_name.py" in bundle.files[0].text


def test_count_tokens_with_special_tokens():
    assert count_tokens("x = '<|endoftext|>'") > 0


def test_count_tokens_offline_fallback(monkeypatch):
    monkeypatch.setattr(diff_module, "_encoding", lambda: None)
    assert count_tokens("a" * 300) == 101


def _file(path: str, lines: int) -> FileDiff:
    body = "\n".join(f"+value_{i} = compute({i})" for i in range(lines))
    return FileDiff(
        path, f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -0,0 +1 @@\n{body}"
    )


def test_fit_to_budget_keeps_everything_when_small():
    files = [_file("a.py", 3), _file("b.py", 3)]
    text, truncated = fit_to_budget(files, 10_000)
    assert truncated == []
    assert text == files[0].text + "\n" + files[1].text


def test_fit_to_budget_truncates_large_file_instead_of_dropping_it():
    small, big = _file("lib/small.py", 2), _file("lib/core.py", 2000)

    text, truncated = fit_to_budget([small, big], 600)

    assert truncated == ["lib/core.py"]
    assert small.text in text
    assert "diff --git a/lib/core.py b/lib/core.py" in text
    assert "more lines truncated" in text
    assert count_tokens(text) <= 650


def test_fit_to_budget_lists_files_that_cannot_fit_at_all():
    files = [_file(f"pkg/module_{i}.py", 50) for i in range(200)]

    text, truncated = fit_to_budget(files, 600)

    assert len(truncated) == 200
    assert "were omitted due to size constraints" in text
    assert "- pkg/module_199.py" in text
