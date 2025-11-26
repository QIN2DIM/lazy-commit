import typer

from smart_commit.git_commit_generator import GitCommitGenerator


app = typer.Typer()


@app.command()
def main(
    push: bool = typer.Option(False, "--push", help="Auto-push after commit"),
    add: bool = typer.Option(False, "--add", help="Only stage and commit without pushing"),
):
    """Generate a git commit message and apply commit with optional auto-push."""
    # When push is enabled, add is automatically enabled
    if push:
        add = True
    # GitCommitGenerator._find_git_root() handles finding git root from any subdirectory
    generator = GitCommitGenerator(auto_push=push, auto_add=add)
    generator.run()


if __name__ == "__main__":
    app()
