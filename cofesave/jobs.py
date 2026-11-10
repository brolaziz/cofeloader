import asyncio
import logging
import time
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import FSInputFile, Message

from cofesave.config import Settings
from cofesave.downloader import DownloadFailure, fetch, resolve_tiktok_short_link
from cofesave.links import VideoLink, tiktok_cache_key
from cofesave.storage import CachedVideo, Storage

logger = logging.getLogger(__name__)


def caption(title: str, platform: str) -> str:
    return f"{title[:180]}\n\n{platform} • @cofesavebot"


class JobManager:
    def __init__(self, settings: Settings, storage: Storage) -> None:
        self.settings = settings
        self.storage = storage
        self.tasks: set[asyncio.Task] = set()
        self.active_downloads = 0
        self.accepting = True

    async def handle(self, message: Message, link: VideoLink) -> None:
        if not message.from_user:
            return
        if not self.accepting:
            return
        task = asyncio.current_task()
        assert task is not None
        self.tasks.add(task)
        try:
            await self.deliver(message, link)
        except DownloadFailure as error:
            logger.info("%s download failed: %s", link.platform, error.code)
            with suppress(TelegramAPIError):
                await message.answer(str(error))
        except TelegramAPIError as error:
            logger.warning("Telegram delivery failed: %s", type(error).__name__)
            with suppress(TelegramAPIError):
                await message.answer("Videoni yuborib bo'lmadi. Keyinroq qayta urinib ko'ring.")
        except Exception as error:
            logger.error("Job failed: %s", type(error).__name__)
            with suppress(TelegramAPIError):
                await message.answer("Xatolik yuz berdi. Keyinroq qayta urinib ko'ring.")
        finally:
            self.tasks.discard(task)

    async def send_cached(self, message: Message, platform: str, key: str) -> bool:
        cached = self.storage.get(key)
        if cached is None:
            return False
        try:
            await message.answer_video(cached.file_id, caption=caption(cached.title, platform))
        except TelegramBadRequest as error:
            # Only invalidate a stale file ID, not unrelated delivery errors.
            if not any(
                term in error.message.lower()
                for term in (
                    "file identifier",
                    "file_id",
                    "wrong remote file",
                    "file reference expired",
                )
            ):
                raise
            if self.storage.get(key) == cached:
                self.storage.discard(key)
            return False
        self.storage.delivered(cached=True)
        return True

    async def deliver(self, message: Message, link: VideoLink) -> None:
        original_url = link.url
        short_tiktok = link.platform == "TikTok" and link.tiktok_id is None
        cache_key = (
            self.storage.alias_for(original_url)
            if short_tiktok
            else tiktok_cache_key(link.tiktok_id)
        )
        if cache_key and await self.send_cached(message, link.platform, cache_key):
            return
        if await self.send_cached(message, link.platform, original_url):
            return

        if short_tiktok and cache_key is None:
            link = await resolve_tiktok_short_link(link)
            resolved_key = tiktok_cache_key(link.tiktok_id)
            if resolved_key:
                for key in (resolved_key, link.url):
                    if await self.send_cached(message, link.platform, key):
                        self.storage.remember_alias(original_url, key)
                        return

        if self.active_downloads >= self.settings.workers:
            await message.answer("Yuklash joylari band. Havolani qayta yuboring.")
            return

        self.active_downloads += 1
        try:
            await self.download_and_send(message, link, original_url if short_tiktok else None)
        finally:
            self.active_downloads -= 1

    async def download_and_send(self, message: Message, link: VideoLink, alias: str | None) -> None:
        with TemporaryDirectory(prefix="cofesave-", dir=self.settings.download_dir) as directory:
            started = time.monotonic()
            video = await fetch(link.url, Path(directory), self.settings)
            downloaded = time.monotonic()
            sent = await message.answer_video(
                FSInputFile(video.path, filename="cofesave.mp4"),
                caption=caption(video.title, link.platform),
                supports_streaming=True,
                request_timeout=120,
            )
            logger.info(
                "%s delivered: download=%.2fs upload=%.2fs",
                link.platform,
                downloaded - started,
                time.monotonic() - downloaded,
            )
            if sent.video:
                key = tiktok_cache_key(video.tiktok_id or link.tiktok_id) or link.url
                self.storage.save(key, CachedVideo(sent.video.file_id, video.title))
                if alias and alias != key:
                    self.storage.remember_alias(alias, key)
            self.storage.delivered(cached=False)

    async def stop(self) -> None:
        self.accepting = False
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
