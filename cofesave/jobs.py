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
from cofesave.formats import DownloadFormat
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

    async def handle(
        self,
        message: Message,
        link: VideoLink,
        selection: DownloadFormat = DownloadFormat.AUTO,
        *,
        menu: Message | None = None,
    ) -> None:
        if not message.from_user:
            return
        if not self.accepting:
            return
        task = asyncio.current_task()
        assert task is not None
        self.tasks.add(task)
        try:
            if await self.deliver(message, link, selection):
                if menu is not None:
                    with suppress(TelegramAPIError):
                        await menu.delete()
                with suppress(TelegramAPIError):
                    await message.delete()
        except DownloadFailure as error:
            logger.info("%s download failed: %s", link.platform, error.code)
            description = str(error)
            if link.platform != "YouTube":
                if error.code == "size":
                    description = "Eng sifatli fayl hajmi limitdan katta. Boshqa video yuboring."
                elif error.code == "format":
                    description = str(DownloadFailure("unavailable"))
            with suppress(TelegramAPIError):
                await message.answer(description)
        except TelegramAPIError as error:
            logger.warning("Telegram delivery failed: %s", type(error).__name__)
            with suppress(TelegramAPIError):
                await message.answer("Faylni yuborib bo'lmadi. Keyinroq qayta urinib ko'ring.")
        except Exception as error:
            logger.error("Job failed: %s", type(error).__name__)
            with suppress(TelegramAPIError):
                await message.answer("Xatolik yuz berdi. Keyinroq qayta urinib ko'ring.")
        finally:
            self.tasks.discard(task)

    async def send_cached(
        self, message: Message, platform: str, key: str, selection: DownloadFormat
    ) -> bool:
        key = selection.cache_key(key, platform)
        cached = self.storage.get(key)
        if cached is None:
            return False
        try:
            send = message.answer_video
            if selection is DownloadFormat.MP3:
                send = message.answer_audio
            elif cached.is_document:
                send = message.answer_document
            await send(cached.file_id, caption=caption(cached.title, platform))
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

    async def deliver(self, message: Message, link: VideoLink, selection: DownloadFormat) -> bool:
        original_url = link.url
        short_tiktok = link.platform == "TikTok" and link.tiktok_id is None
        alias = selection.cache_key(original_url, link.platform)
        cache_key = (
            self.storage.alias_for(alias) if short_tiktok else tiktok_cache_key(link.tiktok_id)
        )
        if cache_key and await self.send_cached(message, link.platform, cache_key, selection):
            return True
        if await self.send_cached(message, link.platform, original_url, selection):
            return True

        if short_tiktok and cache_key is None:
            link = await resolve_tiktok_short_link(link)
            resolved_key = tiktok_cache_key(link.tiktok_id)
            if resolved_key:
                for key in (resolved_key, link.url):
                    if await self.send_cached(message, link.platform, key, selection):
                        self.storage.remember_alias(alias, key)
                        return True

        if self.active_downloads >= self.settings.workers:
            await message.answer("Yuklash joylari band. Birozdan keyin qayta urinib ko'ring.")
            return False

        self.active_downloads += 1
        try:
            await self.download_and_send(
                message, link, selection, original_url if short_tiktok else None
            )
        finally:
            self.active_downloads -= 1
        return True

    async def download_and_send(
        self, message: Message, link: VideoLink, selection: DownloadFormat, alias: str | None
    ) -> None:
        with TemporaryDirectory(prefix="cofesave-", dir=self.settings.download_dir) as directory:
            started = time.monotonic()
            video = await fetch(link.url, Path(directory), self.settings, selection)
            downloaded = time.monotonic()
            extension = video.path.suffix.lower()
            is_document = selection is not DownloadFormat.MP3 and extension != ".mp4"
            upload = FSInputFile(video.path, filename=f"cofesave{extension}")
            description = caption(video.title, link.platform)
            if selection is DownloadFormat.MP3:
                sent = await message.answer_audio(
                    upload,
                    caption=description,
                    title=video.title,
                    request_timeout=self.settings.upload_timeout,
                )
                media = sent.audio
            elif is_document:
                sent = await message.answer_document(
                    upload,
                    caption=description,
                    request_timeout=self.settings.upload_timeout,
                )
                media = sent.document
            else:
                sent = await message.answer_video(
                    upload,
                    caption=description,
                    supports_streaming=True,
                    request_timeout=self.settings.upload_timeout,
                )
                media = sent.video
            logger.info(
                "%s delivered: download=%.2fs upload=%.2fs",
                link.platform,
                downloaded - started,
                time.monotonic() - downloaded,
            )
            if media:
                key = tiktok_cache_key(video.tiktok_id or link.tiktok_id) or link.url
                self.storage.save(
                    selection.cache_key(key, link.platform),
                    CachedVideo(media.file_id, video.title, is_document),
                )
                if alias and alias != key:
                    self.storage.remember_alias(selection.cache_key(alias, link.platform), key)
            self.storage.delivered(cached=False)

    async def stop(self) -> None:
        self.accepting = False
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
