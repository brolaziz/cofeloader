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
