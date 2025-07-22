from pathlib import Path

import typer

from smart_commit.git_commit_generator import GitCommitGenerator


app = typer.Typer()


@app.command()
def main(push: bool = typer.Option(False, "--push", help="Auto-push after commit")):
    """Generate a git commit message and apply commit with optional auto-push."""
    # Check if you are in a git repository
    if not Path(".git").is_dir():
        typer.echo("This script must be run from the root of a Git repository.", err=True)
        raise typer.Exit(1)
    else:
        generator = GitCommitGenerator(auto_push=push)
        generator.run()


if __name__ == "__main__":
    app()
