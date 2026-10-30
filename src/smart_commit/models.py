# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/19 22:43
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from pydantic import BaseModel, Field, field_validator
from rich.cells import cell_len
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
    diff_source: str = Field(..., description="What the diff covers, e.g. staged changes only.")
    language: str = Field(..., description="Natural language of the commit message.")
    excluded_files: list[str] = Field(
        default_factory=list,
        description="Changed noise files (lock files...) left out of the diff.",
    )
    recent_commits: list[str] = Field(
        default_factory=list, description="Subjects of recent commits, as a style reference."
    )
    hint: str | None = Field(default=None, description="Extra context given by the user.")


class CommitMessage(BaseModel):
    """Structured output for the generated commit message."""

    type: str = Field(description="Commit type (e.g., 'feat', 'fix'). Keep as standard English.")
    scope: str | None = Field(
        default=None,
        description="Optional scope of the changes (code module name, usually in English).",
    )
    title: str = Field(
        description="Short, imperative-mood title. MUST be written in the target language specified by the user."
    )
    body: str | None = Field(
        default=None,
        description="Detailed explanation of the changes. MUST be written in the target language specified by the user.",
    )

    @field_validator("type", mode="before")
    @classmethod
    def _normalize_type(cls, value: str) -> str:
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("scope", "body", mode="before")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if isinstance(value, str) else value

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

        # Build the header line with type badge, followed by the body if present
        content = Text()
        content.append(f" {type_style['icon']} ", style=f"bold {type_style['color']}")
        content.append(f"{self.type}", style=f"bold {type_style['color']}")
        if self.scope:
            content.append(f"({self.scope})", style="bold cyan")
        content.append(": ", style="bold white")
        content.append(self.title, style="bold white")

        if self.body:
            content.append("\n\n")
            content.append(self.body, style="dim white")

        # Calculate content width: find the longest line in the commit message.
        # cell_len counts CJK characters as two terminal columns.
        lines = self.to_git_message().split("\n")
        max_content_width = max(cell_len(line) for line in lines) if lines else 0
        # Add padding (4 chars total: 2 on left + 2 on right) + border (2 chars)
        panel_width = min(100, max(60, max_content_width + 6))

        return Panel(
            content,
            title="[bold bright_white]📋 Generated Commit Message[/bold bright_white]",
            border_style=type_style["color"],
            padding=(1, 2),
            width=panel_width,
        )
