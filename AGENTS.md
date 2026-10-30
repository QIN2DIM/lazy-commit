Rules:
- **Python Execution**: Run Python commands and scripts through `uv` (e.g., `uv run`), whether working with project files or running Python scripts bundled in skills.
- **Verification Strategy**: Feel free to write and run lightweight ad-hoc commands or temporary scripts to verify changes by default, and reserve creating, saving, or running `pytest` suites for when explicitly requested by the user.
- **Workspace Scope**: Keep all file creation and modifications within the current project directory, placing any temporary scripts or scratch files inside `./.cache/`.
- **Pythonic Style**: Write concise, elegant, and idiomatic Python with a focus on readability:
  - Keep modules and functions cohesive and well-scoped, leaving simple one- or two-line logic inline rather than splitting it into tiny helpers.
  - Trust internal contracts, types, and invariants directly, favoring straightforward logic over defensive programming.
  - Thoughtfully adopt Python's syntactic sugar and modern language features where they make code cleaner and more expressive.
- **Agent Engineering**: When working on AI agent development tasks, align designs and implementations with OpenAI Harness principles and context management best practices.
