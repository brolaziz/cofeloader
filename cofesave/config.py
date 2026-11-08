import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def integer(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} butun son bo'lishi kerak.") from error
    if not minimum <= value <= maximum:
        raise ValueError(f"{name}: {minimum}–{maximum} oralig'ida bo'lishi kerak.")
    return value


@dataclass(frozen=True)
class Settings:
    token: str
    admin_ids: frozenset[int]
    data_dir: Path
    download_dir: Path
    workers: int
    max_queue: int
    cooldown: int
    max_bytes: int
    max_duration: int
    download_timeout: int
    cookies_file: Path | None = None

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv(ROOT / ".env")
        token = os.getenv("BOT_TOKEN", "").strip()
        if not token:
            raise ValueError(
                "BOT_TOKEN yo'q. .env.example faylidan .env yarating va tokenni yozing."
            )
        try:
            admins = frozenset(
                int(item.strip()) for item in os.getenv("ADMIN_IDS", "").split(",") if item.strip()
            )
        except ValueError as error:
            raise ValueError(
                "ADMIN_IDS faqat raqamli Telegram ID'lardan iborat bo'lishi kerak."
            ) from error
        cookie_value = os.getenv("COOKIES_FILE", "").strip()
        cookies = Path(cookie_value).resolve() if cookie_value else None
        if cookies and not cookies.is_file():
            raise ValueError("COOKIES_FILE fayli topilmadi.")
        return cls(
            token=token,
            admin_ids=admins,
            data_dir=Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve(),
            download_dir=Path(os.getenv("DOWNLOAD_DIR", str(ROOT / "downloads"))).resolve(),
            workers=integer("WORKERS", 2, 1, 4),
            max_queue=integer("MAX_QUEUE_SIZE", 0, 0, 10000),
            cooldown=integer("USER_COOLDOWN_SECONDS", 0, 0, 3600),
            max_bytes=integer("MAX_FILE_MB", 48, 1, 48) * 1_000_000,
            max_duration=integer("MAX_DURATION_SECONDS", 0, 0, 86400),
            download_timeout=integer("DOWNLOAD_TIMEOUT_SECONDS", 180, 10, 600),
            cookies_file=cookies,
        )
