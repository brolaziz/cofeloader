import asyncio
import logging
import time
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import FSInputFile, Message

from cofesave.config import Settings
from cofesave.downloader import DownloadFailure, fetch
from cofesave.links import VideoLink
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

    async def deliver(self, message: Message, link: VideoLink) -> None:
        cached = self.storage.get(link.url)
        if cached:
            try:
                await message.answer_video(
                    cached.file_id, caption=caption(cached.title, link.platform)
                )
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
                if self.storage.get(link.url) == cached:
                    self.storage.discard(link.url)
            else:
                self.storage.delivered(cached=True)
                return
        if self.active_downloads >= self.settings.workers:
            await message.answer("Yuklash joylari band. Havolani qayta yuboring.")
            return

        self.active_downloads += 1
        try:
            await self.download_and_send(message, link)
        finally:
            self.active_downloads -= 1

    async def download_and_send(self, message: Message, link: VideoLink) -> None:
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
                self.storage.save(link.url, CachedVideo(sent.video.file_id, video.title))
            self.storage.delivered(cached=False)

    async def stop(self) -> None:
        self.accepting = False
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
