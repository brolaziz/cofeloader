import sqlite3

from cofesave.storage import CachedVideo, Storage


def test_persistent_cache_and_bot_isolation(tmp_path):
    path = tmp_path / "db.sqlite3"
    first = Storage(path, 1)
    first.add_user(123)
    first.add_user(123)
    first.save("url", CachedVideo("file-a", "title"))
    first.delivered(cached=False)
    first.delivered(cached=True)
    assert first.stats() == (1, 1, 2, 1)
    first.close()
    reopened = Storage(path, 1)
    assert reopened.get("url") == CachedVideo("file-a", "title")
    second = Storage(path, 2)
    assert second.get("url") is None
    assert second.stats() == (0, 0, 0, 0)
    reopened.discard("url")
    assert reopened.get("url") is None
    reopened.close()
    second.close()


def test_migrates_existing_cache_and_persists_document_type(tmp_path):
    path = tmp_path / "db.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE videos (bot_id INTEGER NOT NULL, url TEXT NOT NULL, "
            "file_id TEXT NOT NULL, title TEXT NOT NULL, PRIMARY KEY (bot_id, url))"
        )
        db.execute("INSERT INTO videos VALUES (1, 'old', 'video-id', 'old title')")
    db.close()

    storage = Storage(path, 1)
    assert storage.get("old") == CachedVideo("video-id", "old title")
    storage.save("new", CachedVideo("doc-id", "new title", is_document=True))
    storage.close()

    reopened = Storage(path, 1)
    assert reopened.get("new") == CachedVideo("doc-id", "new title", is_document=True)
    reopened.close()
