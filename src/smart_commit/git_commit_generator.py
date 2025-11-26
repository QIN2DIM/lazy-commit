# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/19 22:43
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""
import fnmatch
import re
import subprocess
from pathlib import Path
from typing import List, Optional

import tiktoken
import typer
from openai import OpenAI
from openai.types.chat import ChatCompletionSystemMessageParam, ChatCompletionUserMessageParam
from rich.console import Console
from rich.text import Text

from smart_commit.models import CommitMessage, LLMInput
from smart_commit.prompts import SYSTEM_INSTRUCTIONS, USER_PROMPT_TEMPLATE
from smart_commit.settings import settings

# Files to exclude from LLM analysis (diff generation) but still allow in commits
# These files create noise in commit message generation due to their verbose changes
EXCLUDED_FILE_PATTERNS = [
    "*.lock",  # All lock files
    "uv.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "poetry.lock",
    "*.ipynb",  # Jupyter notebooks
]

console = Console()


class GitCommitGenerator:
    """A class to generate git commit messages."""

    def __init__(self, auto_push: bool = False, auto_add: bool = False):
        """
        Initializes the generator. Automatically finds the git repository root.
        """
        with console.status("[bold green]Initializing GitCommitGenerator..."):
            self.repo_path = self._find_git_root()
            self.max_context = settings.LAZY_COMMIT_MAX_CONTEXT_SIZE
            self.auto_push = auto_push
            self.auto_add = auto_add

            self._client = OpenAI(
                api_key=settings.LAZY_COMMIT_OPENAI_API_KEY.get_secret_value(),
                base_url=settings.LAZY_COMMIT_OPENAI_BASE_URL,
            )
            self._model = settings.LAZY_COMMIT_OPENAI_MODEL_NAME

        console.print(
            f"[green]✓[/green] GitCommitGenerator initialized for repository: {self.repo_path}"
        )

    @staticmethod
    def _find_git_root() -> Path:
        """
        Finds the root directory of the git repository using git command.
        This handles worktrees, submodules, and allows running from any subdirectory.
        """
        # Use git command as primary method - it's more reliable and handles all git scenarios
        try:
            git_root_str = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"],
                text=True,
                stderr=subprocess.PIPE,
                cwd=Path.cwd(),
            ).strip()
            return Path(git_root_str)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Fallback to manual search for cases where git command fails
            current_path = Path.cwd().resolve()

            # Check exists() instead of is_dir() to handle worktrees
            while True:
                if (current_path / ".git").exists():
                    return current_path

                if current_path.parent == current_path:
                    break

                current_path = current_path.parent
            console.print(
                "[red]✗[/red] Fatal: Not a git repository (or any of the parent directories).",
                style="red",
            )
            raise ValueError("This script must be run from within a Git repository.")

    @staticmethod
    def _is_ignored_or_excluded(file_path: str, ignore_patterns: List[str]) -> bool:
        """Check if a file path matches any ignore pattern or should be excluded."""
        # Check .gitignore patterns
        for pattern in ignore_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True

        # Check excluded file patterns
        for pattern in EXCLUDED_FILE_PATTERNS:
            if fnmatch.fnmatch(file_path, pattern):
                return True

        return False

    @staticmethod
    def _count_tokens(text: str) -> int:
        # tiktoken.encoding_for_model(self._model)

        # Inaccurate value
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))

    @staticmethod
    def _format_file_status(file_path: str, status: str) -> Text:
        """Format file status with appropriate icons and colors, similar to GitHub Desktop."""
        if status == "M":  # Modified
            status_text = "[orange1]M[/orange1]"
        elif status == "A" or status == "?":  # Added/New
            status_text = "[green]A[/green]"
        elif status == "D":  # Deleted
            status_text = "[red]D[/red]"
        else:
            status_text = "[dim]?[/dim]"

        # Create rich text object
        text = Text()
        text.append(f"{status_text} ", style="bold")
        text.append(file_path, style="dim")
        return text

    def _call_llm_api(self, llm_input: LLMInput) -> CommitMessage | None:
        with console.status("[bold blue]Generating commit message with LLM..."):
            user_prompt = USER_PROMPT_TEMPLATE.format(
                branch_name=llm_input.git_branch_name, diff_content=llm_input.diff_content
            )
            messages = [
                ChatCompletionSystemMessageParam(role="system", content=SYSTEM_INSTRUCTIONS),
                ChatCompletionUserMessageParam(role="user", content=user_prompt),
            ]

            completion = self._client.chat.completions.parse(
                model=self._model,
                messages=messages,
                response_format=CommitMessage,
                temperature=0,
                timeout=50,
            )
        console.print("[green]✓[/green] Commit message generated successfully")
        return completion.choices[0].message.parsed

    def _run_command(self, command: List[str], input_: Optional[str] = None) -> str:
        """
        Runs a command, optionally passing stdin, and returns its stdout.

        Args:
            command: The command to run as a list of strings.
            input_: Optional string to be passed as standard input to the command.

        Returns:
            The stdout of the command as a string.
        """
        try:
            # All git commands will be executed under the correct repo_path
            result = subprocess.run(
                command,
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
                encoding="utf8",
                input=input_,
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            console.print(
                f"[red]✗[/red] Command '{' '.join(command)}' failed with error:\n{e.stderr}",
                style="red",
            )
            raise

    def _get_ignore_patterns(self) -> List[str]:
        """Reads .gitignore and .dockerignore and returns a list of patterns."""
        patterns = []
        for ignore_file in [".gitignore", ".dockerignore"]:
            path = self.repo_path / ignore_file
            if path.exists():
                console.print(f"[dim]Reading ignore patterns from '{path}'[/dim]")
                with open(path, "r", encoding="utf8") as f:
                    patterns.extend(
                        line.strip() for line in f if line.strip() and not line.startswith("#")
                    )
        return patterns

    def _get_valid_files(self) -> List[str]:
        """
        Get list of files that should be included in the diff analysis.
        Excludes ignored files and special files completely.
        """
        ignore_patterns = self._get_ignore_patterns()

        # Get all changed files (modified + untracked)
        all_files = []

        # Get modified and staged files
        try:
            modified_files = self._run_command(["git", "diff", "--name-only", "HEAD"])
            if modified_files.strip():
                all_files.extend(f.strip() for f in modified_files.split("\n") if f.strip())
        except subprocess.CalledProcessError:
            # Fallback to just unstaged changes if HEAD doesn't exist (initial commit)
            modified_files = self._run_command(["git", "diff", "--name-only"])
            if modified_files.strip():
                all_files.extend(f.strip() for f in modified_files.split("\n") if f.strip())

        # Get untracked files
        try:
            untracked_files = self._run_command(
                ["git", "ls-files", "--others", "--exclude-standard"]
            )
            if untracked_files.strip():
                all_files.extend(f.strip() for f in untracked_files.split("\n") if f.strip())
        except subprocess.CalledProcessError:
            pass

        # Filter out ignored and excluded files
        valid_files = []
        excluded_files = []

        for file_path in set(all_files):  # Remove duplicates
            if self._is_ignored_or_excluded(file_path, ignore_patterns):
                excluded_files.append(file_path)
            else:
                valid_files.append(file_path)

        # Display excluded files info
        if excluded_files:
            console.print(
                f"[dim]Excluded {len(excluded_files)} files: {', '.join(excluded_files[:5])}{'...' if len(excluded_files) > 5 else ''}[/dim]"
            )

        return valid_files

    def _collect_changes(self) -> str:
        """
        Collects changes from valid files only (excluding special files completely).
        Uses comprehensive git diff to capture all types of changes including directory-level changes.
        """
        valid_files = self._get_valid_files()

        if not valid_files:
            console.print("[yellow]⚠[/yellow] No valid files found for commit.")
            return ""

        console.print(f"[bold blue]📋 Found {len(valid_files)} files with changes:[/bold blue]")
        console.print()

        # Display files with their status
        file_status_dict = {}
        status_output = self._run_command(["git", "status", "--porcelain"])

        if status_output.strip():
            for line in status_output.split("\n"):
                if line.strip():
                    status_code = line[:2]
                    file_path = line[3:].strip()
                    working_tree_status = status_code[1] if len(status_code) > 1 else status_code[0]
                    if working_tree_status == "?":
                        working_tree_status = "A"
                    file_status_dict[file_path] = working_tree_status

        # Get lists of modified and untracked files to determine correct default status
        try:
            modified_files = self._run_command(["git", "diff", "--name-only", "HEAD"])
            modified_files_set = (
                set(f.strip() for f in modified_files.split("\n") if f.strip())
                if modified_files.strip()
                else set()
            )
        except subprocess.CalledProcessError:
            # For initial commit, try different approach
            try:
                modified_files = self._run_command(["git", "diff", "--name-only"])
                modified_files_set = (
                    set(f.strip() for f in modified_files.split("\n") if f.strip())
                    if modified_files.strip()
                    else set()
                )
            except subprocess.CalledProcessError:
                modified_files_set = set()

        try:
            untracked_files = self._run_command(
                ["git", "ls-files", "--others", "--exclude-standard"]
            )
            untracked_files_set = (
                set(f.strip() for f in untracked_files.split("\n") if f.strip())
                if untracked_files.strip()
                else set()
            )
        except subprocess.CalledProcessError:
            untracked_files_set = set()

        for file_path in valid_files:
            # Determine correct status if not found in git status output
            if file_path in file_status_dict:
                status = file_status_dict[file_path]
            elif file_path in untracked_files_set:
                status = "A"  # New/untracked file
            elif file_path in modified_files_set:
                status = "M"  # Modified file
            else:
                # Check if file exists to determine if it's new or modified
                file_full_path = self.repo_path / file_path
                if file_full_path.exists():
                    status = "A"  # Assume new if it exists but wasn't tracked
                else:
                    status = "D"  # Deleted

            status_text = self._format_file_status(file_path, status)
            console.print(f"  {status_text}")

        console.print()

        all_diffs = []

        # Separate tracked and untracked files for different processing
        tracked_files = []
        untracked_files_list = []

        for file_path in valid_files:
            if file_path in untracked_files_set:
                untracked_files_list.append(file_path)
            else:
                tracked_files.append(file_path)

        # Get comprehensive diff for tracked files only
        if tracked_files:
            try:
                # Use -- separator to avoid path ambiguity
                diff_output = self._run_command(["git", "diff", "HEAD", "--"] + tracked_files)
                if diff_output:
                    all_diffs.append(diff_output)
            except subprocess.CalledProcessError:
                # Fallback for initial commit scenario
                try:
                    diff_output = self._run_command(
                        ["git", "diff", "--cached", "--"] + tracked_files
                    )
                    if diff_output:
                        all_diffs.append(diff_output)
                except subprocess.CalledProcessError:
                    pass

                try:
                    unstaged_diff = self._run_command(["git", "diff", "--"] + tracked_files)
                    if unstaged_diff:
                        all_diffs.append(unstaged_diff)
                except subprocess.CalledProcessError:
                    pass

        # Handle new untracked files separately
        for file_path in untracked_files_list:
            try:
                file_full_path = self.repo_path / file_path
                if file_full_path.exists() and file_full_path.is_file():
                    with open(file_full_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    # Create diff format for new files
                    new_file_diff = f"diff --git a/{file_path} b/{file_path}\n"
                    new_file_diff += "new file mode 100644\n"
                    new_file_diff += "index 0000000..0000000\n"
                    new_file_diff += "--- /dev/null\n"
                    new_file_diff += f"+++ b/{file_path}\n"

                    for line in content.splitlines():
                        new_file_diff += f"+{line}\n"

                    all_diffs.append(new_file_diff)
            except (UnicodeDecodeError, IOError) as e:
                console.print(f"[dim]Skipping binary/unreadable file: {file_path} ({e})[/dim]")
                # For binary files, add a simple marker
                new_file_diff = f"diff --git a/{file_path} b/{file_path}\n"
                new_file_diff += "new file mode 100644\n"
                new_file_diff += f"Binary file {file_path} added\n"
                all_diffs.append(new_file_diff)

        if not all_diffs:
            console.print("[yellow]⚠[/yellow] No changes found in valid files.")
            return ""

        console.print(f"[green]✓[/green] Collected diffs for {len(valid_files)} files.")
        return "\n".join(all_diffs)

    def _compress_context(self, diff_content: str) -> str:
        """Compresses the diff content if it exceeds the max length."""
        len_diff_content = self._count_tokens(diff_content)
        if len_diff_content <= self.max_context:
            return diff_content

        with console.status("[bold yellow]Compressing diff content..."):
            console.print(
                f"[yellow]⚠[/yellow] Diff content ({len_diff_content} tokens) exceeds max context length ({self.max_context}). Compressing..."
            )

            # Split by file diffs
            file_diffs = re.split(r"(diff --git .*)", diff_content)
            if file_diffs[0] == "":
                file_diffs = file_diffs[1:]

            # Create file summaries for compression
            file_summaries = []
            for i in range(0, len(file_diffs), 2):
                if i + 1 < len(file_diffs):
                    header = file_diffs[i]
                    content = file_diffs[i + 1]
                    match = re.search(r"b/(.*)", header)
                    if match:
                        file_path = match.group(1).strip()
                        file_summaries.append(
                            {
                                "path": file_path,
                                "header": header,
                                "content": content,
                                "len": len(header) + len(content),
                            }
                        )

            # Sort by length (smallest first)
            file_summaries.sort(key=lambda x: x["len"])

            final_diff_parts = []
            total_len = 0
            files_omitted = []

            for summary in file_summaries:
                diff_part = summary["header"] + summary["content"]
                len_diff_part = self._count_tokens(diff_part)

                if total_len + len_diff_part <= self.max_context:
                    final_diff_parts.append(diff_part)
                    total_len += len_diff_part
                else:
                    files_omitted.append(f"- {summary['path']} (content truncated due to size)")

            if files_omitted:
                summary_header = (
                    "\n--- The following files were omitted due to size constraints ---\n"
                )
                final_diff_parts.append(summary_header + "\n".join(files_omitted))

            compressed_output = "".join(final_diff_parts)

        console.print(
            f"[green]✓[/green] Compressed diff from {len(diff_content)} to {len(compressed_output)} chars."
        )
        return compressed_output

    def _generate_prompt_data(self) -> LLMInput | None:
        """Generates the input data for the LLM."""
        branch_name = self._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        full_diff = self._collect_changes()

        if not full_diff:
            return None

        compressed_diff = self._compress_context(full_diff)

        console.print("[green]✓[/green] Prompt data generated successfully")
        return LLMInput(
            git_branch_name=branch_name,
            diff_content=compressed_diff,
            full_diff_for_reference=full_diff,
        )

    def _apply_commit(self, commit_message: CommitMessage):
        """
        Stages all changed files (including excluded files) and then applies the commit.
        The LLM analysis only considered valid files to avoid noise, but we should commit
        all changed files including those that were manually staged or excluded from analysis.
        """
        message_str = commit_message.to_git_message()
        console.print(f"\n{message_str}\n", style="dim")

        if not self.auto_add:
            return

        try:
            with console.status("[bold green]Applying commit changes..."):
                # Get all changed files (including excluded ones for actual commit)
                all_changed_files = []

                # Get already staged files
                try:
                    staged_files = self._run_command(["git", "diff", "--cached", "--name-only"])
                    if staged_files.strip():
                        all_changed_files.extend(
                            f.strip() for f in staged_files.split("\n") if f.strip()
                        )
                except subprocess.CalledProcessError:
                    pass

                # Get modified files (unstaged)
                try:
                    modified_files = self._run_command(["git", "diff", "--name-only", "HEAD"])
                    if modified_files.strip():
                        all_changed_files.extend(
                            f.strip() for f in modified_files.split("\n") if f.strip()
                        )
                except subprocess.CalledProcessError:
                    # Fallback for initial commit
                    try:
                        modified_files = self._run_command(["git", "diff", "--name-only"])
                        if modified_files.strip():
                            all_changed_files.extend(
                                f.strip() for f in modified_files.split("\n") if f.strip()
                            )
                    except subprocess.CalledProcessError:
                        pass

                # Get untracked files
                try:
                    untracked_files = self._run_command(
                        ["git", "ls-files", "--others", "--exclude-standard"]
                    )
                    if untracked_files.strip():
                        all_changed_files.extend(
                            f.strip() for f in untracked_files.split("\n") if f.strip()
                        )
                except subprocess.CalledProcessError:
                    pass

                # Remove duplicates and filter out .gitignore patterns (but keep excluded patterns)
                ignore_patterns = self._get_ignore_patterns()
                final_files = []

                for file_path in set(all_changed_files):
                    # Only filter out .gitignore patterns, but keep EXCLUDED_FILE_PATTERNS
                    is_gitignored = False
                    for pattern in ignore_patterns:
                        if fnmatch.fnmatch(file_path, pattern):
                            is_gitignored = True
                            break

                    if not is_gitignored:
                        final_files.append(file_path)

                if final_files:
                    # Show what files will be committed
                    valid_files = self._get_valid_files()  # Files that were analyzed by LLM
                    excluded_from_analysis = [f for f in final_files if f not in valid_files]

                    console.print(f"[dim]Staging {len(final_files)} files for commit:[/dim]")
                    if excluded_from_analysis:
                        console.print(
                            f"[dim]  • {len(valid_files)} files were analyzed by LLM[/dim]"
                        )
                        console.print(
                            f"[dim]  • {len(excluded_from_analysis)} files excluded from analysis but included in commit: {', '.join(excluded_from_analysis[:3])}{'...' if len(excluded_from_analysis) > 3 else ''}[/dim]"
                        )

                    # Separate existing and deleted files for proper staging
                    existing_files = []
                    deleted_files = []

                    for file_path in final_files:
                        file_full_path = self.repo_path / file_path
                        if file_full_path.exists():
                            existing_files.append(file_path)
                        else:
                            deleted_files.append(file_path)

                    # Stage existing files with git add
                    if existing_files:
                        self._run_command(["git", "add"] + existing_files)

                    # Stage deleted files with git rm
                    # First, get files that are already staged for deletion to avoid re-staging
                    if deleted_files:
                        # Get already staged deleted files
                        staged_deleted_set = set()
                        try:
                            staged_deleted = self._run_command(
                                ["git", "diff", "--cached", "--name-only", "--diff-filter=D"]
                            )
                            if staged_deleted.strip():
                                staged_deleted_set = set(
                                    f.strip() for f in staged_deleted.split("\n") if f.strip()
                                )
                        except subprocess.CalledProcessError:
                            pass

                        # Get files that are tracked by git (in the index)
                        tracked_files_set = set()
                        try:
                            tracked_files = self._run_command(["git", "ls-files"])
                            if tracked_files.strip():
                                tracked_files_set = set(
                                    f.strip() for f in tracked_files.split("\n") if f.strip()
                                )
                        except subprocess.CalledProcessError:
                            pass

                        # Filter: only rm files that are tracked and not already staged for deletion
                        files_to_rm = [
                            f
                            for f in deleted_files
                            if f not in staged_deleted_set and f in tracked_files_set
                        ]

                        if files_to_rm:
                            self._run_command(["git", "rm"] + files_to_rm)
                else:
                    console.print("[yellow]⚠[/yellow] No files to commit.")
                    return

                # Commit with message
                self._run_command(["git", "commit", "-F", "-"], input_=message_str)

            console.print("[green]✓[/green] Commit applied successfully!")

            # Push if auto-push is enabled
            if self.auto_push:
                self._push_changes()

        except subprocess.CalledProcessError as e:
            console.print(
                f"[red]✗[/red] Failed to apply commit. Git output:\n{e.stdout}\n{e.stderr}",
                style="red",
            )

    def _push_changes(self):
        """Push the committed changes to the remote repository."""
        try:
            with console.status("[bold magenta]Pushing changes to remote repository..."):
                # Get current branch name
                current_branch = self._run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])

                # Push to origin with the current branch
                self._run_command(["git", "push", "origin", current_branch])

            console.print(
                f"[green]✓[/green] Successfully pushed changes to origin/{current_branch}"
            )

        except subprocess.CalledProcessError as e:
            console.print(
                f"[red]✗[/red] Failed to push changes. Git output:\n{e.stdout}\n{e.stderr}",
                style="red",
            )
            raise

    def run(self):
        """Main execution flow."""
        try:
            console.print("[bold blue]🚀 Starting smart commit process...[/bold blue]")

            # 1. Generate prompt data (includes collecting and compressing changes)
            if not (llm_input := self._generate_prompt_data()):
                console.print("[yellow]⚠[/yellow] No changes to commit. Exiting.")
                return

            # 2. Call LLM to get a structured commit message
            if not (commit_message_obj := self._call_llm_api(llm_input)):
                console.print("[red]✗[/red] Failed to generate commit message.")
                return

            # 3. Apply the commit
            self._apply_commit(commit_message_obj)

            console.print(
                "[bold green]🎉 Smart commit process completed successfully![/bold green]"
            )

        except Exception as e:
            console.print(f"[red]✗[/red] An unexpected error occurred: {e}", style="red")
            raise typer.Exit(1)
