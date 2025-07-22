# lazy-commit
A git commit message generator for personal use.

Installation:

```bash
uv tool install lazy-commit
```

Set env:
```bash
export SMART_COMMIT_OPENAI_BASE_URL=
export SMART_COMMIT_OPENAI_API_KEY=
export SMART_COMMIT_OPENAI_MODEL_NAME=
```

Invoke tool:

```bash
uv run commit
```

Gen commit and push:

```bash
uv run commit --push
```

