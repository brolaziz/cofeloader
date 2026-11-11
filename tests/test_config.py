import pytest

from cofesave.config import Settings


def test_missing_token_fails_clearly(monkeypatch):
    monkeypatch.setattr("cofesave.config.load_dotenv", lambda *_: None)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="BOT_TOKEN"):
        Settings.load()


@pytest.mark.parametrize("value", ["0", "49", "not-a-number"])
def test_cloud_settings_reject_invalid_size_limits(value, monkeypatch):
    monkeypatch.setattr("cofesave.config.load_dotenv", lambda *_: None)
    monkeypatch.setenv("BOT_TOKEN", "test-placeholder")
    monkeypatch.delenv("TELEGRAM_LOCAL_API_URL", raising=False)
    monkeypatch.setenv("MAX_FILE_MB", value)
    with pytest.raises(ValueError, match="MAX_FILE_MB"):
        Settings.load()


def test_large_file_settings_require_separate_api(monkeypatch):
    monkeypatch.setattr("cofesave.config.load_dotenv", lambda *_: None)
    monkeypatch.setenv("BOT_TOKEN", "test-placeholder")
    monkeypatch.setenv("MAX_FILE_MB", "2000")
    monkeypatch.delenv("DOWNLOAD_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("UPLOAD_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("TELEGRAM_LOCAL_API_URL", "https://api.telegram.org")
    with pytest.raises(ValueError, match="TELEGRAM_LOCAL_API_URL"):
        Settings.load()

    monkeypatch.setenv("TELEGRAM_LOCAL_API_URL", "http://bot-api.internal:8081/")
    settings = Settings.load()
    assert settings.telegram_local_api_url == "http://bot-api.internal:8081"
    assert settings.max_bytes == 2_000_000_000
    assert settings.download_timeout == settings.upload_timeout == 1800

    monkeypatch.setenv("MAX_FILE_MB", "2001")
    with pytest.raises(ValueError, match="MAX_FILE_MB"):
        Settings.load()


def test_invalid_admin_id_rejected(monkeypatch):
    monkeypatch.setattr("cofesave.config.load_dotenv", lambda *_: None)
    monkeypatch.setenv("BOT_TOKEN", "test-placeholder")
    monkeypatch.setenv("ADMIN_IDS", "@username")
    with pytest.raises(ValueError, match="ADMIN_IDS"):
        Settings.load()
