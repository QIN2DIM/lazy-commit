# lazy-commit

A smart git commit message generator that uses AI to create high-quality commit messages following the Conventional Commits specification. It analyzes your git changes and automatically generates descriptive commit messages.

## Features

- 🤖 **AI-Powered**: Uses OpenAI-compatible APIs to generate intelligent commit messages
- 📝 **Conventional Commits**: Follows the Conventional Commits specification format
- 🌐 **Multi-Language Support**: Generate commit messages in any natural language (English, 简体中文, 日本語, etc.)
- 🎯 **Smart File Analysis**: Automatically analyzes changed files and generates appropriate diffs
- 🧺 **Staged-Only Mode**: `--staged` uses only hand-picked staged changes, like `git commit`
- 🚫 **Intelligent Filtering**: Excludes lock files and binary files from analysis while still including them in commits
- ⚡ **Context Compression**: Shortens large diffs to fit the token budget without dropping any file
- 🔁 **Provider Compatibility**: Falls back to JSON mode when a server doesn't support structured outputs
- 🔄 **Auto-Push Support**: Optional automatic push to remote repository after commit
- 🎨 **Rich UI**: Beautiful command-line interface with progress bars and status indicators
- 📊 **File Status Display**: Shows modified, added, and deleted files with clear indicators

## Installation

### Using uv (recommended)

```bash
uv tool install lazy-commit
```

```bash
uv tool upgrade lazy-commit
```

### From source

```bash
git clone https://github.com/QIN2DIM/lazy-commit.git
cd lazy-commit
uv sync
```

## Configuration

Set the required environment variables:

```bash
# For OpenAI API
export LAZY_COMMIT_OPENAI_BASE_URL="https://api.openai.com/v1"
export LAZY_COMMIT_OPENAI_API_KEY="your-openai-api-key"
export LAZY_COMMIT_OPENAI_MODEL_NAME="gpt-4o-mini"

# For free models via OpenRouter
export LAZY_COMMIT_OPENAI_BASE_URL="https://openrouter.ai/api/v1"
export LAZY_COMMIT_OPENAI_API_KEY="sk-or-v1-xxx"
export LAZY_COMMIT_OPENAI_MODEL_NAME="moonshotai/kimi-k2:free"

# For Chinese users - free models via ModelScope
export LAZY_COMMIT_OPENAI_BASE_URL="https://api-inference.modelscope.cn/v1"
export LAZY_COMMIT_OPENAI_API_KEY="ms-xxx"
export LAZY_COMMIT_OPENAI_MODEL_NAME="Qwen/Qwen3-30B-A3B-Instruct-2507"

# Optional: Token budget for the diff sent to the model (default: 32000)
export LAZY_COMMIT_MAX_CONTEXT_SIZE=32000

# Optional: Timeout in seconds for one LLM request, retried once (default: 120)
export LAZY_COMMIT_TIMEOUT=120

# Optional: Extra comma-separated patterns to leave out of the analyzed diff,
# on top of the built-in lock file patterns (they are still committed)
export LAZY_COMMIT_EXCLUDE_PATTERNS="*.snap,generated/*"

# Optional: Bypass system proxy for LAN endpoints (default: false)
# Useful when accessing internal model endpoints via VPN
export LAZY_COMMIT_BYPASS_PROXY=true

# Optional: Set the language for commit messages (default: English)
# Supports any natural language like "English", "简体中文", "日本語", "Español", etc.
export LAZY_COMMIT_LANGUAGE="简体中文"
```

### Environment File

You can also create a `.env` file in your project root. Its `LAZY_COMMIT_*` values take
precedence over exported variables, so exports in your shell profile act as global defaults
and each project can override them (it is found from any subdirectory):

**For OpenRouter (free models):**
```env
LAZY_COMMIT_OPENAI_BASE_URL=https://openrouter.ai/api/v1
LAZY_COMMIT_OPENAI_API_KEY=sk-or-v1-xxx
LAZY_COMMIT_OPENAI_MODEL_NAME=moonshotai/kimi-k2:free
LAZY_COMMIT_LANGUAGE=English
```

**For Chinese users - [ModelScope](https://www.modelscope.cn/models/Qwen/Qwen3-30B-A3B-Instruct-2507) (free models):**
```env
LAZY_COMMIT_OPENAI_BASE_URL="https://api-inference.modelscope.cn/v1"
LAZY_COMMIT_OPENAI_API_KEY="ms-xxx"
LAZY_COMMIT_OPENAI_MODEL_NAME="Qwen/Qwen3-30B-A3B-Instruct-2507"
LAZY_COMMIT_LANGUAGE=简体中文
```

## Language Configuration

You can generate commit messages in any natural language by setting the `LAZY_COMMIT_LANGUAGE` environment variable.

### Supported Languages

The tool supports any natural language. Simply specify the language name in your preferred format:

```bash
# English (default)
export LAZY_COMMIT_LANGUAGE="English"

# Simplified Chinese
export LAZY_COMMIT_LANGUAGE="简体中文"

# Japanese
export LAZY_COMMIT_LANGUAGE="日本語"

# Spanish
export LAZY_COMMIT_LANGUAGE="Español"

# French
export LAZY_COMMIT_LANGUAGE="Français"

# German
export LAZY_COMMIT_LANGUAGE="Deutsch"
```

The AI model will automatically generate commit messages in the specified language, including both the title and body.

## Usage

### Basic Usage

lazy-commit uses all your changes, including untracked files, with their latest content.
Pass `--staged` to only use the changes you have staged, like `git commit` does.

Generate a commit message only (display it and copy it to the clipboard):

```bash
commit
```

or if installed from source:

```bash
uv run commit
```

### Commit

Generate a commit message, stage all changes and commit:

```bash
commit --add
```

Only commit what you have already staged (e.g. after `git add -p`):

```bash
commit --add --staged
```

If the model call or a git hook fails, the staging area is restored to how it was.

### Auto-push After Commit

Generate commit message, stage files, apply commit, and push to remote:

```bash
commit --push
```

Note: When `--push` is enabled, `--add` is automatically enabled. The branch's upstream is
used; without one, the branch is pushed to `origin` and set as upstream.

### More Options

```bash
commit --hint "users reported timeouts on slow networks"  # extra context for the model
commit --lang 日本語                                      # override LAZY_COMMIT_LANGUAGE once
commit --print                                            # print only the message to stdout
git commit -e -m "$(commit --print --staged)"             # e.g. review it in your editor
commit --version
```

## How It Works

1. **Repository Detection**: Automatically detects git repository root
2. **File Analysis**: Reads staged, modified, renamed and untracked files with one `git status` call
3. **Scope Selection**: Uses all changes, or only the staged ones with `--staged`
4. **Smart Filtering**: Leaves lock files, `*.ipynb`, minified files and binaries out of the diff, but tells the model they changed and still commits them
5. **Context Management**: Keeps small diffs whole and shortens the largest ones to fit the token budget
6. **AI Generation**: Sends the diff, branch name and recent commit subjects (as a style reference) to the model
7. **Display Message**: Always displays the generated commit message
8. **Optional Commit**: With `--add`, commits exactly what was analyzed
9. **Optional Push**: With `--push`, pushes to the branch's upstream after the commit

## Commit Message Format

The tool generates commit messages following the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

### Commit Types

- `feat`: New features
- `fix`: Bug fixes
- `docs`: Documentation changes
- `style`: Code style changes (formatting, etc.)
- `refactor`: Code refactoring
- `perf`: Performance improvements
- `test`: Test additions or modifications
- `build`: Build system changes
- `ci`: CI/CD changes
- `chore`: Maintenance tasks

## Examples

### Feature Addition
```
feat(api): add user authentication endpoint

Implements JWT-based authentication with login and logout functionality.
Includes input validation and error handling for invalid credentials.
```

### Bug Fix
```
fix(payment): correct tax calculation error

Fixed off-by-one error in tax calculation loop that was causing
incorrect tax amounts for orders with multiple items.
```

### Documentation
```
docs(README): update installation and configuration instructions

Added detailed setup guide for environment variables and
included examples for different AI providers.
```

## Requirements

- Python 3.12+
- Git repository
- OpenAI-compatible API access (OpenAI, local models, etc.)

## Dependencies

- `typer`: Command-line interface
- `openai`: OpenAI API client
- `pydantic-settings`: Configuration management
- `rich`: Beautiful terminal output
- `tiktoken`: Token counting

## Development

### Setup Development Environment

```bash
git clone https://github.com/QIN2DIM/lazy-commit.git
cd lazy-commit
uv sync --group dev
```

### Tests

The tests run against real temporary git repositories with a fake model, so no API key is needed:

```bash
uv run pytest --cov=smart_commit
```

### Code Quality

```bash
# Format code
uv run black src/ tests/

# Lint code
uv run ruff check src/ tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Run code quality checks
6. Submit a pull request

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
