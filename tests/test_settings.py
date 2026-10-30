from smart_commit.settings import SmartCommitSettings

from .conftest import write


def test_reads_prefixed_keys_from_dotenv(tmp_path, monkeypatch):
    write(
        tmp_path,
        ".env",
        "LAZY_COMMIT_OPENAI_BASE_URL=http://10.0.0.2:8000/v1\n"
        "LAZY_COMMIT_LANGUAGE=日本語\n"
        "LAZY_COMMIT_MAX_CONTEXT_SIZE=2000\n"
        "MAX_CONTEXT_SIZE=1\n",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LAZY_COMMIT_LANGUAGE", "简体中文")

    settings = SmartCommitSettings()

    assert settings.LAZY_COMMIT_OPENAI_BASE_URL == "http://10.0.0.2:8000/v1"
    assert settings.LAZY_COMMIT_LANGUAGE == "简体中文"  # the environment wins over .env
    assert settings.LAZY_COMMIT_MAX_CONTEXT_SIZE == 2000
    assert settings.LAZY_COMMIT_OPENAI_MODEL_NAME == "local-model"


def test_defaults_for_official_openai(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = SmartCommitSettings()
    assert settings.is_official_openai
    assert settings.LAZY_COMMIT_OPENAI_MODEL_NAME == "gpt-4.1-mini"
    # No placeholder key: a missing key is reported instead of failing with a 401
    assert settings.LAZY_COMMIT_OPENAI_API_KEY is None
