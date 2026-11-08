import pytest

from cofesave.config import Settings, integer


def test_missing_token_fails_clearly(monkeypatch):
    monkeypatch.setattr("cofesave.config.load_dotenv", lambda *_: None)
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    with pytest.raises(ValueError, match="BOT_TOKEN"):
        Settings.load()


@pytest.mark.parametrize("value", ["0", "49", "not-a-number"])
def test_upload_limit_cannot_exceed_telegram_limit(value, monkeypatch):
    monkeypatch.setenv("MAX_FILE_MB", value)
    with pytest.raises(ValueError, match="MAX_FILE_MB"):
        integer("MAX_FILE_MB", 48, 1, 48)


def test_invalid_admin_id_rejected(monkeypatch):
    monkeypatch.setattr("cofesave.config.load_dotenv", lambda *_: None)
    monkeypatch.setenv("BOT_TOKEN", "test-placeholder")
    monkeypatch.setenv("ADMIN_IDS", "@username")
    with pytest.raises(ValueError, match="ADMIN_IDS"):
        Settings.load()
