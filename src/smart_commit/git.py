# -*- coding: utf-8 -*-
"""
@Desc    : Thin wrapper around the git CLI whose output is safe to parse.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from smart_commit import LazyCommitError

# Keep `git diff` output parseable whatever the user's git config says
# (color.ui=always, diff.noprefix, diff.mnemonicPrefix, diff.external, ...).
DIFF_FLAGS = ["--no-color", "--no-ext-diff", "--src-prefix=a/", "--dst-prefix=b/", "-M"]


class GitError(LazyCommitError):
    """A git command exited with a non-zero status."""

    def __init__(self, args: tuple[str, ...], returncode: int, stdout: str, stderr: str):
        self.stdout = stdout
        self.stderr = stderr
        output = stderr.strip() or stdout.strip() or f"exit status {returncode}"
        super().__init__(f"`git {' '.join(args)}` failed:\n{output}")


@dataclass(frozen=True)
class FileChange:
    """One entry of `git status --porcelain=v2`."""

    path: str
    index: str  # staged status (X); "." when unchanged, "?" when untracked
    worktree: str  # unstaged status (Y); "." when unchanged, "?" when untracked
    orig_path: str | None = None  # source path of a rename or copy
    conflicted: bool = False

    @property
    def untracked(self) -> bool:
        return self.index == "?"

    @property
    def staged(self) -> bool:
        return self.index not in (".", "?") and not self.conflicted

    @property
    def status_code(self) -> str:
        """Single-letter status of the file compared with HEAD, for display."""
        if self.untracked:
            return "A"
        if self.index in ("A", "R", "C") or self.worktree == ".":
            return self.index
        return self.worktree


@dataclass
class RepoStatus:
    branch: str | None = None  # None when HEAD is detached
    has_commits: bool = True
    upstream: str | None = None
    changes: list[FileChange] = field(default_factory=list)

    @property
    def staged(self) -> list[FileChange]:
        return [c for c in self.changes if c.staged]

    @property
    def conflicts(self) -> list[FileChange]:
        return [c for c in self.changes if c.conflicted]


def parse_status(output: str) -> RepoStatus:
    """Parse `git status --porcelain=v2 -z --branch` output."""
    status = RepoStatus()
    tokens = iter(output.split("\0"))
    for token in tokens:
        match token[:1]:
            case "#":
                key, _, value = token[2:].partition(" ")
                if key == "branch.oid":
                    status.has_commits = value != "(initial)"
                elif key == "branch.head":
                    status.branch = None if value == "(detached)" else value
                elif key == "branch.upstream":
                    status.upstream = value
            case "1":  # 1 XY sub mH mI mW hH hI path
                parts = token.split(" ", 8)
                status.changes.append(FileChange(parts[8], *parts[1]))
            case "2":  # 2 XY sub mH mI mW hH hI Xscore path NUL origPath
                parts = token.split(" ", 9)
                status.changes.append(FileChange(parts[9], *parts[1], orig_path=next(tokens)))
            case "u":  # u XY sub m1 m2 m3 mW h1 h2 h3 path
                parts = token.split(" ", 10)
                status.changes.append(FileChange(parts[10], *parts[1], conflicted=True))
            case "?":
                status.changes.append(FileChange(token[2:], "?", "?"))
    return status


class GitRepo:
    """Git operations on one working tree. All commands run from the repository root."""

    def __init__(self, root: Path):
        self.root = root

    @classmethod
    def discover(cls, cwd: Path | None = None) -> "GitRepo":
        """Find the repository containing `cwd` (works from any subdirectory or worktree)."""
        try:
            root = cls(cwd or Path.cwd()).run("rev-parse", "--show-toplevel")
        except GitError as e:
            raise LazyCommitError(f"Not inside a git work tree ({e.stderr.strip()}).") from e
        return cls(Path(root.strip()))

    def run(self, *args: str, input_: str | None = None, errors: str = "replace") -> str:
        """
        Run git and return its stdout without stripping it.

        Output is read as bytes and decoded leniently, so files in GBK or other legacy
        encodings never crash the tool. Use errors="surrogateescape" for output whose
        paths are handed back to git, so non-UTF-8 file names round-trip unchanged.
        """
        try:
            proc = subprocess.run(
                # quotePath=false: print non-ASCII paths as-is instead of "\344\270\255"
                ["git", "-c", "core.quotePath=false", *args],
                cwd=self.root,
                input=input_.encode("utf-8") if input_ is not None else None,
                capture_output=True,
            )
        except FileNotFoundError as e:
            raise LazyCommitError("git executable not found. Please install git first.") from e

        stdout = proc.stdout.decode("utf-8", errors=errors)
        if proc.returncode != 0:
            raise GitError(args, proc.returncode, stdout, proc.stderr.decode("utf-8", "replace"))
        return stdout

    def status(self) -> RepoStatus:
        return parse_status(
            self.run(
                "status",
                "--porcelain=v2",
                "-z",
                "--branch",
                "--untracked-files=all",
                errors="surrogateescape",
            )
        )

    def diff(self, status: RepoStatus, staged_only: bool) -> str:
        """Staged changes, or all tracked changes in the working tree compared with HEAD."""
        if staged_only:  # `--cached` also works before the first commit
            return self.run("diff", "--cached", *DIFF_FLAGS)
        # Without commits, compare with the empty tree (its id differs between SHA-1 and SHA-256)
        base = (
            "HEAD"
            if status.has_commits
            else self.run("hash-object", "-t", "tree", "--stdin", input_="").strip()
        )
        return self.run("diff", *DIFF_FLAGS, base, "--")

    def recent_subjects(self, status: RepoStatus, limit: int = 10) -> list[str]:
        if not status.has_commits:
            return []
        return self.run("log", f"-{limit}", "--no-merges", "--format=%s").splitlines()

    def push(self, status: RepoStatus) -> str:
        """Push the current branch and return a description of where it went."""
        if status.branch is None:
            raise LazyCommitError("HEAD is detached; refusing to push.")
        if status.upstream:
            self.run("push")
            return status.upstream

        remotes = self.run("remote").split()
        if not remotes:
            raise LazyCommitError("No git remote is configured.")
        remote = "origin" if "origin" in remotes else remotes[0]
        self.run("push", "--set-upstream", remote, status.branch)
        return f"{remote}/{status.branch}"
