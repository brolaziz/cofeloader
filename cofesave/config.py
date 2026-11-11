import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

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


def local_api_url() -> str | None:
    value = os.getenv("TELEGRAM_LOCAL_API_URL", "").strip()
    if not value:
        return None
    error_message = "TELEGRAM_LOCAL_API_URL alohida Bot API serverining HTTP(S) manzilini kutadi."
    try:
        parts = urlsplit(value)
        hostname, port = parts.hostname, parts.port
    except ValueError as error:
        raise ValueError(error_message) from error
    if (
        parts.scheme not in {"http", "https"}
        or not hostname
        or hostname.rstrip(".") == "api.telegram.org"
        or port == 0
        or parts.username is not None
        or parts.query
        or parts.fragment
        or any(char.isspace() for char in value)
    ):
        raise ValueError(error_message)
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    token: str
    admin_ids: frozenset[int]
    data_dir: Path
    download_dir: Path
    workers: int
    max_bytes: int
    max_duration: int
    download_timeout: int
    cookies_file: Path | None = None
    telegram_local_api_url: str | None = None
    upload_timeout: int = 120

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
        api_url = local_api_url()
        max_file_mb = integer("MAX_FILE_MB", 48, 1, 2000 if api_url else 48)
        large_files = max_file_mb > 48
        return cls(
            token=token,
            admin_ids=admins,
            data_dir=Path(os.getenv("DATA_DIR", str(ROOT / "data"))).resolve(),
            download_dir=Path(os.getenv("DOWNLOAD_DIR", str(ROOT / "downloads"))).resolve(),
            workers=integer("WORKERS", 2, 1, 4),
            max_bytes=max_file_mb * 1_000_000,
            max_duration=integer("MAX_DURATION_SECONDS", 0, 0, 86400),
            download_timeout=integer(
                "DOWNLOAD_TIMEOUT_SECONDS",
                1800 if large_files else 180,
                10,
                3600 if api_url else 600,
            ),
            cookies_file=cookies,
            telegram_local_api_url=api_url,
            upload_timeout=integer(
                "UPLOAD_TIMEOUT_SECONDS", 1800 if large_files else 120, 10, 3600
            ),
        )
