# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/19 22:43
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    : The commit workflow: collect changes, ask the LLM, then commit and push.
"""

import sys

import pyperclip
from rich.console import Console
from rich.markup import escape

from smart_commit import LazyCommitError
from smart_commit.diff import DEFAULT_EXCLUDE_PATTERNS, collect_changes, fit_to_budget
from smart_commit.git import GitRepo, RepoStatus
from smart_commit.llm import CommitMessageGenerator
from smart_commit.models import CommitMessage, LLMInput
from smart_commit.settings import SmartCommitSettings

# UI goes to stderr so stdout stays clean for --print. Always escape() paths, git output and
# error messages put into markup: "app/[slug]/page.tsx" would otherwise lose "[slug]".
console = Console(stderr=True)

_STATUS_COLORS = {
    "M": "orange1",
    "T": "orange1",
    "A": "green",
    "D": "red",
    "R": "cyan",
    "C": "cyan",
}


def _preview(paths: list[str], limit: int = 5) -> str:
    return escape(", ".join(paths[:limit]) + ("..." if len(paths) > limit else ""))


class GitCommitGenerator:
    """A class to generate git commit messages."""

    def __init__(
        self,
        repo: GitRepo,
        settings: SmartCommitSettings,
        llm: CommitMessageGenerator,
        *,
        auto_add: bool = False,
        auto_push: bool = False,
        staged_only: bool = False,
        print_only: bool = False,
        hint: str | None = None,
        language: str | None = None,
    ):
        """
        Args:
            auto_add: Stage all changes and commit them.
            auto_push: Push after committing; implies auto_add.
            staged_only: Only use (and commit) what is already staged, like `git commit`.
            print_only: Write only the raw message to stdout, for scripts and git hooks.
            hint: Extra context for the model, e.g. why the change was made.
            language: Overrides LAZY_COMMIT_LANGUAGE.
        """
        self.repo = repo
        self.settings = settings
        self.llm = llm
        self.auto_push = auto_push
        self.auto_add = auto_add or auto_push
        self.staged_only = staged_only
        self.print_only = print_only
        self.hint = hint
        self.language = language or settings.LAZY_COMMIT_LANGUAGE

    def run(self) -> CommitMessage | None:
        """Main execution flow. Raises LazyCommitError on any failure."""
        console.print(
            f"[bold blue]🚀 Starting smart commit process in[/bold blue] {escape(str(self.repo.root))}"
        )
        status = self.repo.status()
        if status.conflicts:
            paths = [c.path for c in status.conflicts]
            raise LazyCommitError(f"Resolve merge conflicts first: {', '.join(paths)}")
        if not status.changes:
            console.print("[yellow]⚠[/yellow] No changes to commit.")
            return None

        if self.staged_only and not status.staged:
            console.print("[yellow]⚠[/yellow] No staged changes to commit.")
            return None

        staged_only = self.staged_only
        saved_index = None
        committed = False
        try:
            if self.auto_add and not staged_only:
                # Stage first so the commit contains exactly what the model has seen, even if
                # files change while waiting for the LLM. The index snapshot (a tree object)
                # lets us put the staging area back as it was if anything fails.
                saved_index = self.repo.run("write-tree").strip()
                self.repo.run("add", "--all")
                status = self.repo.status()
                staged_only = True

            if not (message := self._generate(status, staged_only)):
                console.print("[yellow]⚠[/yellow] No changes to commit.")
                return None
            self._output(message)

            if self.auto_add:
                with console.status("[bold green]Applying commit changes..."):
                    output = self.repo.run("commit", "--file=-", input_=message.to_git_message())
                committed = True
                console.print("[green]✓[/green] Commit applied successfully!")
                console.print(f"[dim]{escape(output.strip().splitlines()[0])}[/dim]")
        finally:
            if saved_index and not committed:
                self.repo.run("read-tree", saved_index)  # leaves the working tree untouched
                console.print("[dim]Staging area restored to its previous state.[/dim]")

        if self.auto_push:
            try:
                with console.status("[bold magenta]Pushing changes to remote repository..."):
                    target = self.repo.push(status)
            except LazyCommitError as e:
                raise LazyCommitError(f"The commit was created, but pushing failed: {e}") from e
            console.print(f"[green]✓[/green] Successfully pushed changes to {escape(target)}")

        console.print("[bold green]🎉 Smart commit process completed successfully![/bold green]")
        return message

    def _show_changes(self, status: RepoStatus, staged_only: bool) -> None:
        """Format file status with appropriate icons and colors, similar to GitHub Desktop."""
        changes = status.staged if staged_only else status.changes
        scope = "staged files" if self.staged_only else "files with changes"
        console.print(f"[bold blue]📋 Found {len(changes)} {scope}:[/bold blue]\n")
        for change in changes:
            code = change.index if staged_only else change.status_code
            source = f"{escape(change.orig_path)} → " if change.orig_path else ""
            color = _STATUS_COLORS.get(code, "dim")
            console.print(
                f"  [bold {color}]{code}[/bold {color}] [dim]{source}{escape(change.path)}[/dim]"
            )
        console.print()

        if staged_only and (left_out := [c.path for c in status.changes if c.worktree != "."]):
            console.print(
                f"[dim]Not included: unstaged changes in {len(left_out)} files "
                f"({_preview(left_out, 3)}). Drop --staged to include them.[/dim]"
            )

    def _generate(self, status: RepoStatus, staged_only: bool) -> CommitMessage | None:
        self._show_changes(status, staged_only)

        extra_patterns = self.settings.LAZY_COMMIT_EXCLUDE_PATTERNS.split(",")
        patterns = DEFAULT_EXCLUDE_PATTERNS + tuple(p.strip() for p in extra_patterns if p.strip())
        bundle = collect_changes(self.repo, status, staged_only, patterns)
        if not bundle.files and not bundle.excluded:
            return None
        if bundle.excluded:
            excluded = [f.path for f in bundle.excluded]
            console.print(
                f"[dim]Excluded {len(excluded)} files from analysis: {_preview(excluded)}[/dim]"
            )

        max_tokens = self.settings.LAZY_COMMIT_MAX_CONTEXT_SIZE
        diff_content, truncated = fit_to_budget(bundle.files, max_tokens)
        if truncated:
            console.print(
                f"[yellow]⚠[/yellow] Diff exceeds {max_tokens} tokens; shortened "
                f"{len(truncated)} large files: {_preview(truncated, 3)}"
            )

        llm_input = LLMInput(
            git_branch_name=status.branch or "(detached HEAD)",
            diff_content=diff_content or "(no diff: only lock or generated files changed)",
            diff_source=(
                "staged changes, git diff --cached"
                if staged_only
                else "all uncommitted changes, including untracked files"
            ),
            language=self.language,
            excluded_files=[f"{f.path} ({f.stat})" for f in bundle.excluded],
            recent_commits=self.repo.recent_subjects(status),
            hint=self.hint,
        )
        with console.status("[bold blue]Generating commit message with LLM..."):
            message = self.llm.generate(llm_input)
        console.print("[green]✓[/green] Commit message generated successfully")
        return message

    def _output(self, message: CommitMessage) -> None:
        if self.print_only:
            # Always UTF-8 (what git expects), even when Windows pipes default to a code page
            sys.stdout.flush()
            sys.stdout.buffer.write(f"{message.to_git_message()}\n".encode("utf-8"))
            sys.stdout.buffer.flush()
            return

        console.print()
        console.print(message.to_rich_panel())
        console.print()
        if self.auto_add:
            return
        try:
            pyperclip.copy(message.to_git_message())
        except Exception as e:  # no clipboard on headless Linux / SSH sessions
            console.print(f"[yellow]⚠[/yellow] Failed to copy to clipboard: {escape(str(e))}")
        else:
            console.print("[green]✓[/green] Commit message copied to clipboard!")
