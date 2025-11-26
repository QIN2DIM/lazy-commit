import typer

from smart_commit.git_commit_generator import GitCommitGenerator


app = typer.Typer()


@app.command()
def main(
    push: bool = typer.Option(False, "--push", "-p", help="Auto-push after commit"),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Generate message only, copy to clipboard, don't commit"
    ),
):
    """
    Generate smart git commit messages with AI.

    \b
    Usage modes:
      commit         Auto commit mode - generate and commit automatically
      commit --push  Auto push mode - generate, commit, and push
      commit -n      Dry run mode - only generate and copy to clipboard
    """
    add = True
    # Dry run takes precedence
    if dry_run:
        add = False
        push = False
    # GitCommitGenerator._find_git_root() handles finding git root from any subdirectory
    generator = GitCommitGenerator(auto_push=push, auto_add=add, dry_run=dry_run)
    generator.run()


if __name__ == "__main__":
    app()
