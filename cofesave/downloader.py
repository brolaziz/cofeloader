import asyncio
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

from aiohttp import ClientError, ClientSession, ClientTimeout

from cofesave.config import ROOT, Settings
from cofesave.formats import DownloadFormat
from cofesave.links import VideoLink, parse_link

ERRORS = {
    "size": "Fayl hajmi limitdan katta. Pastroq sifatni tanlang yoki qisqaroq video yuboring.",
    "duration": "Video davomiyligi limitdan uzun. Qisqaroq video yuboring.",
    "live": "Jonli efirni yuklab bo'lmaydi. Tayyor video havolasini yuboring.",
    "restricted": "Bu video yopiq yoki akkauntga kirishni talab qiladi.",
    "platform_blocked": (
        "Platforma botning so'rovini chekladi. Keyinroq qayta urinib ko'ring."
    ),
    "format": "Bu format mavjud emas. Boshqa sifatni yoki avtomatik videoni tanlang.",
    "unavailable": "Videoni olib bo'lmadi. Havolani tekshiring yoki keyinroq urinib ko'ring.",
    "timeout": "Yuklash juda uzoq davom etdi. Keyinroq yoki qisqaroq video bilan urinib ko'ring.",
}


class DownloadFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code if code in ERRORS else "unavailable"
        super().__init__(ERRORS[self.code])


@dataclass(frozen=True)
class DownloadedVideo:
    path: Path
    title: str
    tiktok_id: str | None = None


async def resolve_tiktok_short_link(link: VideoLink) -> VideoLink:
    """Read the first redirect without following it or downloading media."""
    try:
        async with ClientSession(timeout=ClientTimeout(total=3)) as session:
            async with session.get(link.url, allow_redirects=False) as response:
                location = response.headers.get("Location")
                if not 300 <= response.status < 400 or not location:
                    return link
        target = parse_link(urljoin(link.url, location))
    except (ClientError, TimeoutError, ValueError):
        return link
    return target if target.tiktok_id else link


def directory_size(directory: Path) -> int:
    size = 0
    for path in directory.rglob("*"):
        try:
            if path.is_file():
                size += path.stat().st_size
        except FileNotFoundError:
            # FFmpeg / yt-dlp may rename a file between enumeration and stat.
            continue
    return size


def read_result(directory: Path, max_bytes: int) -> DownloadedVideo:
    result_path = directory / "result.json"
    if not result_path.is_file():
        raise DownloadFailure("unavailable")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("error"):
        raise DownloadFailure(result["error"])
    path = (directory / result["filename"]).resolve()
    if path.parent != directory.resolve() or not path.is_file():
        raise DownloadFailure("unavailable")
    if path.stat().st_size > max_bytes:
        raise DownloadFailure("size")
    return DownloadedVideo(path, result["title"], result.get("tiktok_id"))


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if os.name == "nt":
        if process.returncode is None:
            killer = await asyncio.create_subprocess_exec(
                "taskkill",
                "/PID",
                str(process.pid),
                "/T",
                "/F",
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            await killer.wait()
    else:
        # Kill ffmpeg children too, including when the worker exited just before cancellation.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    await process.wait()


async def fetch(
    url: str, directory: Path, settings: Settings, selection: DownloadFormat = DownloadFormat.AUTO
) -> DownloadedVideo:
    command = [
        sys.executable,
        "-m",
        "cofesave.worker",
        url,
        str(directory),
        str(settings.max_bytes),
        str(settings.max_duration),
        "--format",
        selection.value,
    ]
    if settings.cookies_file:
        command.extend(["--cookies", str(settings.cookies_file)])
    environment = os.environ.copy()
    environment.pop("BOT_TOKEN", None)
    environment.pop("ADMIN_IDS", None)
    platform_options = (
        {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=ROOT,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **platform_options,
    )
    try:
        async with asyncio.timeout(settings.download_timeout):
            while process.returncode is None:
                try:
                    await asyncio.wait_for(process.wait(), timeout=0.5)
                except TimeoutError:
                    size = await asyncio.to_thread(directory_size, directory)
                    if size > settings.max_bytes * 3:
                        raise DownloadFailure("size") from None
    except TimeoutError as error:
        raise DownloadFailure("timeout") from error
    finally:
        # Reap the entire process group before TemporaryDirectory cleanup.
        await stop_process(process)
    if process.returncode != 0:
        raise DownloadFailure("unavailable")
    return await asyncio.to_thread(read_result, directory, settings.max_bytes)
