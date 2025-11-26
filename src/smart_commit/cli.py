import typer

from smart_commit.git_commit_generator import GitCommitGenerator


app = typer.Typer()


@app.command()
def main(
    push: bool = typer.Option(False, "--push", "-p", help="Auto-push after commit"),
    add: bool = typer.Option(False, "--add", "-a", help="Stage and commit changes"),
):
    """
    Generate smart git commit messages with AI.

    \b
    Usage modes:
      commit         Generate message only (copy to clipboard)
      commit --add   Stage and commit changes
      commit --push  Stage, commit and push changes
    """
    # When push is enabled, add is automatically enabled
    if push:
        add = True
    # GitCommitGenerator._find_git_root() handles finding git root from any subdirectory
    generator = GitCommitGenerator(auto_push=push, auto_add=add)
    generator.run()


if __name__ == "__main__":
    app()
