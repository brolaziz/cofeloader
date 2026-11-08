import asyncio
import hashlib
import logging
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import FSInputFile, Message

from cofesave.config import Settings
from cofesave.downloader import DownloadFailure, fetch
from cofesave.links import VideoLink
from cofesave.storage import CachedVideo, Storage

logger = logging.getLogger(__name__)


@dataclass
class Job:
    message: Message
    status: Message
    link: VideoLink
    user_id: int


def caption(title: str, platform: str) -> str:
    return f"{title[:180]}\n\n{platform} • @cofesavebot"


class JobManager:
    def __init__(self, settings: Settings, storage: Storage) -> None:
        self.settings = settings
        self.storage = storage
        self.queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=settings.max_queue)
        self.busy: set[int] = set()
        self.cooldowns: dict[int, float] = {}
        self.tasks: list[asyncio.Task] = []
        # Bounded locks deduplicate simultaneous requests for the same canonical URL.
        self.locks = [asyncio.Lock() for _ in range(64)]
        self.accepting = True

    def start(self) -> None:
        self.tasks = [asyncio.create_task(self.worker()) for _ in range(self.settings.workers)]

    async def enqueue(self, message: Message, link: VideoLink) -> None:
        if not message.from_user:
            return
        user_id = message.from_user.id
        if not self.accepting:
            await message.answer("Bot qayta ishga tushmoqda. Birozdan keyin urinib ko'ring.")
            return
        if self.queue.full():
            await message.answer("Navbat to'lgan. Birozdan keyin qayta urinib ko'ring.")
            return
        self.busy.add(user_id)
        try:
            status = await message.answer("Havola qabul qilindi. Navbatda kuting…")
            self.queue.put_nowait(Job(message, status, link, user_id))
        except BaseException:
            self.busy.discard(user_id)
            raise

    async def worker(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                stripe = int.from_bytes(hashlib.sha256(job.link.url.encode()).digest()[:2]) % 64
                async with self.locks[stripe]:
                    await self.process(job)
            except asyncio.CancelledError:
                await self.status(job, "Bot qayta ishga tushmoqda. Havolani qayta yuboring.")
                raise
            except DownloadFailure as error:
                await self.status(job, str(error))
            except TelegramAPIError as error:
                logger.warning("Telegram delivery failed: %s", type(error).__name__)
                await self.status(job, "Videoni yuborib bo'lmadi. Keyinroq qayta urinib ko'ring.")
            except Exception as error:
                logger.error("Job failed: %s", type(error).__name__)
                await self.status(job, "Xatolik yuz berdi. Keyinroq qayta urinib ko'ring.")
            finally:
                self.busy.discard(job.user_id)
                self.queue.task_done()

    async def status(self, job: Job, text: str) -> None:
        with suppress(TelegramAPIError):
            await job.status.edit_text(text)

    async def process(self, job: Job) -> None:
        cached = self.storage.get(job.link.url)
        if cached:
            try:
                await job.message.answer_video(
                    cached.file_id, caption=caption(cached.title, job.link.platform)
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
                self.storage.discard(job.link.url)
            else:
                self.storage.delivered(cached=True)
                with suppress(TelegramAPIError):
                    await job.status.delete()
                return
        await self.status(job, f"{job.link.platform} videosi yuklanmoqda…")
        with TemporaryDirectory(prefix="cofesave-", dir=self.settings.download_dir) as directory:
            video = await fetch(job.link.url, Path(directory), self.settings)
            await self.status(job, "Video tayyor. Telegram'ga yuborilmoqda…")
            sent = await job.message.answer_video(
                FSInputFile(video.path, filename="cofesave.mp4"),
                caption=caption(video.title, job.link.platform),
                supports_streaming=True,
                request_timeout=120,
            )
            if sent.video:
                self.storage.save(job.link.url, CachedVideo(sent.video.file_id, video.title))
            self.storage.delivered(cached=False)
        with suppress(TelegramAPIError):
            await job.status.delete()

    async def stop(self) -> None:
        self.accepting = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        while not self.queue.empty():
            job = self.queue.get_nowait()
            await self.status(job, "Bot qayta ishga tushmoqda. Havolani qayta yuboring.")
            self.queue.task_done()
        self.busy.clear()
