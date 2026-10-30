# -*- coding: utf-8 -*-
"""
@Desc    : Turn repository changes into a size-bounded diff for the LLM.
"""

import fnmatch
import os
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from smart_commit.git import GitRepo, RepoStatus

# Files to exclude from LLM analysis (diff generation) but still allow in commits.
# These files create noise in commit message generation due to their verbose changes.
# Patterns without "/" match the file name in any directory, like .gitignore does.
DEFAULT_EXCLUDE_PATTERNS = (
    "*.lock",  # uv, poetry, yarn, Cargo, composer, Gemfile, ...
    "package-lock.json",
    "npm-shrinkwrap.json",
    "pnpm-lock.yaml",
    "bun.lockb",
    "go.sum",
    "*.ipynb",  # Jupyter notebooks
    "*.min.js",
    "*.min.css",
    "*.map",
)

# Untracked files are read by us rather than git; cap what goes into memory and the prompt.
MAX_UNTRACKED_BYTES = 256 * 1024
# Same heuristic as git: a NUL byte near the start of a file means it is binary.
_BINARY_SNIFF_BYTES = 8000

_FILE_HEADER = re.compile(r"^(?=diff --git )", re.MULTILINE)
_PATH_LINE_PREFIXES = ("rename to ", "copy to ", "--- ", "+++ ")


@dataclass
class FileDiff:
    path: str
    text: str

    @property
    def stat(self) -> str:
        added = removed = 0
        for line in self.text.splitlines():
            if line.startswith("+") and not line.startswith("+++ "):
                added += 1
            elif line.startswith("-") and not line.startswith("--- "):
                removed += 1
        return f"+{added} -{removed}"


@dataclass
class DiffBundle:
    files: list[FileDiff] = field(default_factory=list)  # analyzed by the LLM
    excluded: list[FileDiff] = field(default_factory=list)  # noise: only summarized


def is_excluded(path: str, patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS) -> bool:
    """Check if a file path should be excluded from LLM analysis (e.g. lock files)."""
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(path if "/" in p else name, p) for p in patterns)


def _unquote(path: str) -> str:
    """Undo git's C-style quoting, used for paths containing quotes, backslashes or controls."""
    if not path.startswith('"'):
        return path
    escapes = {'"': '"', "\\": "\\", "t": "\t", "n": "\n"}
    return re.sub(r"\\(.)", lambda m: escapes.get(m.group(1), m.group(0)), path[1:-1])


def _chunk_path(chunk: str) -> str:
    """Extract the (new) path from one `diff --git` chunk."""
    lines = chunk.split("\n", 12)
    for line in lines[1:]:
        if line.startswith("@@"):
            break
        if (prefix := next((p for p in _PATH_LINE_PREFIXES if line.startswith(p)), None)) is None:
            continue
        path = _unquote(line[len(prefix) :].rstrip("\t"))
        if prefix in ("rename to ", "copy to "):
            return path
        if path != "/dev/null":
            return path[2:]  # strip the a/ or b/ prefix

    # Binary or mode-only changes have no ---/+++ lines; the header is "a/<p> b/<p>".
    header = lines[0][len("diff --git ") :]
    n = (len(header) - 5) // 2
    if header[2 + n : 5 + n] == " b/":
        return header[2 : 2 + n]
    return header


def split_diff(diff: str) -> list[FileDiff]:
    """Split multi-file diff output into per-file chunks."""
    # Anchored at line start: inside a chunk every content line starts with " ", "+", "-",
    # "\" or "@@", so a line beginning with "diff --git " is always a real file header.
    return [
        FileDiff(_chunk_path(chunk), chunk.rstrip("\n"))
        for chunk in _FILE_HEADER.split(diff)
        if chunk.startswith("diff --git ")
    ]


def untracked_file_diff(root: Path, path: str) -> FileDiff:
    """Build a new-file diff for an untracked file without touching the index."""
    full_path = root / path
    header = f"diff --git a/{path} b/{path}\n"
    if full_path.is_symlink():
        return FileDiff(path, f"{header}new file mode 120000\n+{os.readlink(full_path)}")
    if full_path.is_dir():  # a nested git repository is listed as "sub/"
        return FileDiff(path, f"{header}new directory (nested repository)")
    size = full_path.stat().st_size
    with open(full_path, "rb") as f:
        data = f.read(MAX_UNTRACKED_BYTES)

    if b"\0" in data[:_BINARY_SNIFF_BYTES]:
        return FileDiff(path, f"{header}new file mode 100644\nBinary file added ({size} bytes)")

    lines = data.decode("utf-8", errors="replace").splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    text = f"{header}new file mode 100644\n--- /dev/null\n+++ b/{path}\n"
    text += f"@@ -0,0 +1,{len(lines)} @@\n{body}"
    if size > MAX_UNTRACKED_BYTES:
        text += f"\n... [file truncated, {size} bytes in total]"
    return FileDiff(path, text)


def collect_changes(
    repo: GitRepo,
    status: RepoStatus,
    staged_only: bool,
    exclude_patterns: tuple[str, ...] = DEFAULT_EXCLUDE_PATTERNS,
) -> DiffBundle:
    """Collect per-file diffs and separate out noise files like lock files."""
    files = split_diff(repo.diff(status, staged_only))
    if not staged_only:
        files += [untracked_file_diff(repo.root, c.path) for c in status.changes if c.untracked]

    bundle = DiffBundle()
    for file_diff in files:
        target = bundle.excluded if is_excluded(file_diff.path, exclude_patterns) else bundle.files
        target.append(file_diff)
    return bundle


@cache
def _encoding():
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except Exception:  # tiktoken downloads its vocabulary on first use, which fails offline
        return None


def count_tokens(text: str) -> int:
    """Approximate token count (the exact tokenizer of the configured model is unknown)."""
    encoding = _encoding()
    if encoding is None:
        # Conservative fallback: ~4 ASCII chars or ~1 CJK char per token.
        return len(text.encode("utf-8")) // 3 + 1
    # disallowed_special=(): diffs may legitimately contain strings like "<|endoftext|>"
    return len(encoding.encode(text, disallowed_special=()))


def _truncate(file_diff: FileDiff, allowance: int, size: int) -> str | None:
    """Cut a file diff down to roughly `allowance` tokens; None if even its header won't fit."""
    text = file_diff.text
    header_end = text.find("\n@@")
    if header_end == -1:
        header_end = len(text)
    cut = text.rfind("\n", 0, len(text) * allowance // size)
    if cut <= header_end:
        return None
    omitted = text.count("\n", cut + 1) + 1
    return f"{text[:cut]}\n... [{omitted} more lines truncated]"


def fit_to_budget(files: list[FileDiff], max_tokens: int) -> tuple[str, list[str]]:
    """
    Join file diffs so the result stays within `max_tokens`.

    Small files are kept whole; the remaining budget is shared evenly by the large ones,
    which are truncated instead of dropped, because the largest diff is usually the most
    important part of a change. Returns the text and the paths that were cut.
    """
    sizes = [count_tokens(f.text) for f in files]
    if sum(sizes) <= max_tokens:
        return "\n".join(f.text for f in files), []

    allowance = {}
    budget, remaining = max_tokens, len(files)
    for i in sorted(range(len(files)), key=sizes.__getitem__):
        allowance[i] = min(sizes[i], budget // remaining)
        budget -= allowance[i]
        remaining -= 1

    parts, truncated, omitted = [], [], []
    for i, file_diff in enumerate(files):  # keep git's file order
        if allowance[i] >= sizes[i]:
            parts.append(file_diff.text)
        elif (part := _truncate(file_diff, allowance[i], sizes[i])) is not None:
            parts.append(part)
            truncated.append(file_diff.path)
        else:
            omitted.append(file_diff.path)

    if omitted:
        listing = "\n".join(f"- {path}" for path in omitted)
        parts.append(
            f"--- Diffs of these files were omitted due to size constraints ---\n{listing}"
        )
    return "\n".join(parts), truncated + omitted
