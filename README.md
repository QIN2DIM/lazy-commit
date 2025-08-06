# lazy-commit

A smart git commit message generator that uses AI to create high-quality commit messages following the Conventional Commits specification. It analyzes your git changes and automatically generates descriptive commit messages.

## Features

- 🤖 **AI-Powered**: Uses OpenAI-compatible APIs to generate intelligent commit messages
- 📝 **Conventional Commits**: Follows the Conventional Commits specification format
- 🎯 **Smart File Analysis**: Automatically analyzes changed files and generates appropriate diffs
- 🚫 **Intelligent Filtering**: Excludes lock files and binary files from analysis while still including them in commits
- ⚡ **Context Compression**: Automatically compresses large diffs to fit within token limits
- 🔄 **Auto-Push Support**: Optional automatic push to remote repository after commit
- 🎨 **Rich UI**: Beautiful command-line interface with progress bars and status indicators
- 📊 **File Status Display**: Shows modified, added, and deleted files with clear indicators

## Installation

### Using uv (recommended)

```bash
uv tool install lazy-commit
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
export LAZY_COMMIT_OPENAI_MODEL_NAME="Qwen/Qwen3-Coder-480B-A35B-Instruct"

# Optional: Set maximum context size (default: 32000)
export LAZY_COMMIT_MAX_CONTEXT_SIZE=32000
```

### Environment File

You can also create a `.env` file in your project root:

**For OpenRouter (free models):**
```env
LAZY_COMMIT_OPENAI_BASE_URL=https://openrouter.ai/api/v1
LAZY_COMMIT_OPENAI_API_KEY=sk-or-v1-xxx
LAZY_COMMIT_OPENAI_MODEL_NAME=moonshotai/kimi-k2:free
```

**For Chinese users - [ModelScope](https://www.modelscope.cn/models/Qwen/Qwen3-Coder-480B-A35B-Instruct) (free models):**
```env
LAZY_COMMIT_OPENAI_BASE_URL="https://api-inference.modelscope.cn/v1"
LAZY_COMMIT_OPENAI_API_KEY="ms-xxx"
LAZY_COMMIT_OPENAI_MODEL_NAME="Qwen/Qwen3-Coder-480B-A35B-Instruct"
```

## Usage

### Basic Usage

Generate a commit message only (display message without applying):

```bash
commit
```

or if installed from source:

```bash
uv run commit
```

### Stage and Commit

Generate commit message, stage files, and apply commit (without push):

```bash
commit --add
```

### Auto-push After Commit

Generate commit message, stage files, apply commit, and push to remote:

```bash
commit --push
```

Note: When `--push` is enabled, `--add` is automatically enabled.

## How It Works

1. **Repository Detection**: Automatically detects git repository root
2. **File Analysis**: Scans for modified, staged, and untracked files
3. **Smart Filtering**: Excludes files like `*.lock`, `*.ipynb` from AI analysis but includes them in commits
4. **Diff Generation**: Creates comprehensive diffs for all relevant changes
5. **Context Management**: Compresses large diffs to fit within AI model context limits
6. **AI Generation**: Uses AI to generate a structured commit message following Conventional Commits
7. **Display Message**: Always displays the generated commit message
8. **Optional Staging & Commit**: If `--add` is used, stages all changes and applies the generated commit message
9. **Optional Push**: If `--push` is used, pushes changes to remote repository after commit

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
- `loguru`: Logging
- `tiktoken`: Token counting

## Development

### Setup Development Environment

```bash
git clone https://github.com/QIN2DIM/lazy-commit.git
cd lazy-commit
uv sync --group dev
```

### Code Quality

```bash
# Format code
uv run black src/

# Lint code
uv run ruff check src/
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
