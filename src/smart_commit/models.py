# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/19 22:43
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from pydantic import BaseModel, Field
from rich.console import Group
from rich.panel import Panel
from rich.text import Text


# Commit type styling configuration
COMMIT_TYPE_STYLES = {
    "feat": {"icon": "✨", "color": "bright_green", "label": "Feature"},
    "fix": {"icon": "🐛", "color": "bright_red", "label": "Bug Fix"},
    "docs": {"icon": "📚", "color": "bright_blue", "label": "Documentation"},
    "style": {"icon": "💄", "color": "bright_magenta", "label": "Style"},
    "refactor": {"icon": "♻️", "color": "bright_cyan", "label": "Refactor"},
    "perf": {"icon": "⚡", "color": "bright_yellow", "label": "Performance"},
    "test": {"icon": "🧪", "color": "bright_white", "label": "Test"},
    "build": {"icon": "📦", "color": "orange1", "label": "Build"},
    "ci": {"icon": "🔧", "color": "purple", "label": "CI"},
    "chore": {"icon": "🔨", "color": "dim", "label": "Chore"},
    "revert": {"icon": "⏪", "color": "red", "label": "Revert"},
}


class LLMInput(BaseModel):
    """Model for data passed to the LLM generation module."""

    git_branch_name: str = Field(...)
    diff_content: str = Field(..., description="Formatted and potentially compressed git diff.")
    full_diff_for_reference: str | None = Field(
        default=None, description="The full, uncompressed diff."
    )


class CommitMessage(BaseModel):
    """Structured output for the generated commit message."""

    type: str = Field(..., description="Commit type (e.g., 'feat', 'fix').")
    scope: str | None = Field(default=None, description="Optional scope of the changes.")
    title: str = Field(..., description="Short, imperative-mood title.")
    body: str | None = Field(default=None, description="Detailed explanation of the changes.")

    def to_git_message(self) -> str:
        """Formats the object into a git-commit-ready string."""
        header = f"{self.type}"
        if self.scope:
            header += f"({self.scope})"
        header += f": {self.title}"

        message_parts = [header]
        if self.body:
            message_parts.append(f"\n{self.body}")

        return "\n".join(message_parts)

    def to_rich_panel(self) -> Panel:
        """Formats the commit message as a rich Panel for enhanced display."""
        type_style = COMMIT_TYPE_STYLES.get(
            self.type.lower(), {"icon": "📝", "color": "white", "label": self.type}
        )

        # Build the header line with type badge
        header_text = Text()
        header_text.append(f" {type_style['icon']} ", style=f"bold {type_style['color']}")
        header_text.append(f"{self.type}", style=f"bold {type_style['color']}")
        if self.scope:
            header_text.append(f"({self.scope})", style="bold cyan")
        header_text.append(": ", style="bold white")
        header_text.append(self.title, style="bold white")

        # Build the body if present
        content_parts = [header_text]
        if self.body:
            body_text = Text()
            body_text.append("\n\n")
            body_text.append(self.body, style="dim white")
            content_parts.append(body_text)

        # Create panel with styled border
        return Panel(
            Group(*content_parts),
            title="[bold bright_white]📋 Generated Commit Message[/bold bright_white]",
            border_style=type_style["color"],
            padding=(1, 2),
        )
