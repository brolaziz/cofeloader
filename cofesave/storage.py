import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachedVideo:
    file_id: str
    title: str
    is_document: bool = False


class Storage:
    def __init__(self, path: Path, bot_id: int) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.bot_id = bot_id
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                bot_id INTEGER NOT NULL, user_id INTEGER NOT NULL,
                PRIMARY KEY (bot_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS videos (
                bot_id INTEGER NOT NULL, url TEXT NOT NULL, file_id TEXT NOT NULL,
                title TEXT NOT NULL, is_document INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (bot_id, url)
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                bot_id INTEGER NOT NULL, cached INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS video_aliases (
                bot_id INTEGER NOT NULL, url TEXT NOT NULL, cache_key TEXT NOT NULL,
                PRIMARY KEY (bot_id, url)
            );
        """)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            columns = {column[1] for column in self.db.execute("PRAGMA table_info(videos)")}
            if "is_document" not in columns:
                self.db.execute(
                    "ALTER TABLE videos ADD COLUMN is_document INTEGER NOT NULL DEFAULT 0"
                )

    def add_user(self, user_id: int) -> None:
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO users VALUES (?, ?)", (self.bot_id, user_id))

    def get(self, url: str) -> CachedVideo | None:
        row = self.db.execute(
            "SELECT file_id, title, is_document FROM videos WHERE bot_id=? AND url=?",
            (self.bot_id, url),
        ).fetchone()
        return CachedVideo(row[0], row[1], bool(row[2])) if row else None

    def alias_for(self, url: str) -> str | None:
        row = self.db.execute(
            "SELECT cache_key FROM video_aliases WHERE bot_id=? AND url=?", (self.bot_id, url)
        ).fetchone()
        return row[0] if row else None

    def remember_alias(self, url: str, cache_key: str) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO video_aliases VALUES (?, ?, ?)",
                (self.bot_id, url, cache_key),
            )

    def save(self, url: str, video: CachedVideo) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO videos (bot_id, url, file_id, title, is_document) "
                "VALUES (?, ?, ?, ?, ?)",
                (self.bot_id, url, video.file_id, video.title, video.is_document),
            )

    def discard(self, url: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM videos WHERE bot_id=? AND url=?", (self.bot_id, url))

    def delivered(self, cached: bool) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO deliveries (bot_id, cached) VALUES (?, ?)", (self.bot_id, cached)
            )

    def stats(self) -> tuple[int, int, int, int]:
        users = self.db.execute(
            "SELECT COUNT(*) FROM users WHERE bot_id=?", (self.bot_id,)
        ).fetchone()[0]
        videos = self.db.execute(
            "SELECT COUNT(*) FROM videos WHERE bot_id=?", (self.bot_id,)
        ).fetchone()[0]
        sent, cached = self.db.execute(
            "SELECT COUNT(*), COALESCE(SUM(cached), 0) FROM deliveries WHERE bot_id=?",
            (self.bot_id,),
        ).fetchone()
        return users, videos, sent, cached

    def close(self) -> None:
        self.db.close()
