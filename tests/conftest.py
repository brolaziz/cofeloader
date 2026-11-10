from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cofesave.config import Settings
from cofesave.storage import Storage


@pytest.fixture
def settings(tmp_path):
    downloads = tmp_path / "downloads"
    downloads.mkdir()
    return Settings(
        token="123456:local-test-placeholder",
        admin_ids=frozenset({1}),
        data_dir=tmp_path,
        download_dir=downloads,
        workers=2,
        max_bytes=48_000_000,
        max_duration=1200,
        download_timeout=180,
    )


@pytest.fixture
def storage(tmp_path):
    store = Storage(tmp_path / "test.sqlite3", 123456)
    yield store
    store.close()


@pytest.fixture
def message():
    status = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
    sent = SimpleNamespace(video=SimpleNamespace(file_id="telegram-file-123"))
    return SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(return_value=status),
        answer_video=AsyncMock(return_value=sent),
    )
