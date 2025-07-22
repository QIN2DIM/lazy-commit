# -*- coding: utf-8 -*-
"""
@Time    : 2025/7/19 22:43
@Author  : QIN2DIM
@GitHub  : https://github.com/QIN2DIM
@Desc    :
"""

from pydantic import BaseModel, Field


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
