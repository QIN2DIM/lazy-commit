from importlib.metadata import version as package_version

import typer
from dotenv import dotenv_values
from rich.markup import escape

from smart_commit import LazyCommitError
from smart_commit.git import GitRepo
from smart_commit.git_commit_generator import GitCommitGenerator, console
from smart_commit.llm import CommitMessageGenerator
from smart_commit.settings import SmartCommitSettings

# Locals in tracebacks could include secrets such as the API key
app = typer.Typer(pretty_exceptions_show_locals=False)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"lazy-commit {package_version('lazy-commit')}")
        raise typer.Exit()


@app.command()
def main(
    push: bool = typer.Option(False, "--push", "-p", help="Commit, then push (implies --add)"),
    add: bool = typer.Option(False, "--add", "-a", help="Stage all changes and commit them"),
    staged: bool = typer.Option(
        False, "--staged", "-s", help="Only use staged changes, like `git commit` (e.g. in hooks)"
    ),
    print_only: bool = typer.Option(
        False, "--print", help="Only print the raw message to stdout (for scripts and git hooks)"
    ),
    hint: str | None = typer.Option(
        None, "--hint", "-H", help="Extra context for the model, e.g. why the change was made"
    ),
    language: str | None = typer.Option(
        None, "--lang", "-l", help="Language of the message, overrides LAZY_COMMIT_LANGUAGE"
    ),
    version: bool = typer.Option(
        False, "--version", callback=_show_version, is_eager=True, help="Show version and exit"
    ),
):
    """
    Generate smart git commit messages with AI.

    \b
    Usage modes:
      commit           Generate message only (copy to clipboard)
      commit --add     Stage all changes and commit
      commit --push    Stage, commit and push changes
      commit --staged  Only use what is already staged (combine with the above)
    """
    if print_only and (add or push):
        raise typer.BadParameter("--print can't be combined with --add or --push")

    try:
        repo = GitRepo.discover()
        # The repository's .env beats exported variables: exports in the shell profile act as
        # global defaults, the project's .env tunes them per repository (from any subdirectory).
        # Only LAZY_COMMIT_* keys are taken, and as init kwargs rather than via os.environ, so
        # the project's other variables don't leak into git hooks.
        project_env = {
            key: value
            for key, value in dotenv_values(repo.root / ".env").items()
            if key.startswith("LAZY_COMMIT_") and value
        }
        # Loaded here rather than at import, so invalid values are reported like other errors
        settings = SmartCommitSettings(**project_env)
        generator = GitCommitGenerator(
            repo,
            settings,
            CommitMessageGenerator(settings),
            auto_add=add,
            auto_push=push,
            staged_only=staged,
            print_only=print_only,
            hint=hint,
            language=language,
        )
        generator.run()
    except LazyCommitError as e:
        console.print(f"[red]✗ {escape(str(e))}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(
            f"[red]✗ An unexpected error occurred: {escape(f'{type(e).__name__}: {e}')}[/red]"
        )
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
