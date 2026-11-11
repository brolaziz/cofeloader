import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendVideo

from cofesave.downloader import DownloadedVideo, DownloadFailure
from cofesave.formats import DownloadFormat
from cofesave.jobs import JobManager
from cofesave.links import parse_link
from cofesave.storage import CachedVideo

LINK = parse_link("https://youtu.be/dQw4w9WgXcQ")
TIKTOK_SHORT = parse_link("https://vt.tiktok.com/ZExample/")
TIKTOK_FULL = parse_link("https://www.tiktok.com/@creator/video/7663144858546277655")


@pytest.mark.parametrize("short_first", [True, False])
async def test_tiktok_short_and_full_links_share_cache(
    short_first, settings, storage, message, monkeypatch
):
    async def download(url, directory, config, selection):
        path = directory / "video.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "TikTok", TIKTOK_FULL.tiktok_id)

    fetch = AsyncMock(side_effect=download)
    # The short-first case exercises the downloader's own redirect handling.
    resolve = AsyncMock(return_value=TIKTOK_SHORT if short_first else TIKTOK_FULL)
    monkeypatch.setattr("cofesave.jobs.fetch", fetch)
    monkeypatch.setattr("cofesave.jobs.resolve_tiktok_short_link", resolve)
    manager = JobManager(settings, storage)
    first, second = (TIKTOK_SHORT, TIKTOK_FULL) if short_first else (TIKTOK_FULL, TIKTOK_SHORT)

    await manager.handle(message, first)
    await manager.handle(message, second)
    await manager.handle(message, TIKTOK_SHORT)

    fetch.assert_awaited_once()
    resolve.assert_awaited_once_with(TIKTOK_SHORT)
    assert message.answer_video.call_args.args[0] == "telegram-file-123"
    assert storage.stats()[1:] == (1, 3, 2)


async def test_tiktok_short_link_uses_legacy_full_url_cache(
    settings, storage, message, monkeypatch
):
    storage.save(TIKTOK_FULL.url, CachedVideo("old-file", "TikTok"))
    download = AsyncMock()
    resolve = AsyncMock(return_value=TIKTOK_FULL)
    monkeypatch.setattr("cofesave.jobs.fetch", download)
    monkeypatch.setattr("cofesave.jobs.resolve_tiktok_short_link", resolve)
    manager = JobManager(settings, storage)

    await manager.handle(message, TIKTOK_SHORT)
    await manager.handle(message, TIKTOK_SHORT)

    download.assert_not_awaited()
    resolve.assert_awaited_once()
    assert message.answer_video.call_args.args[0] == "old-file"


async def test_busy_download_returns_immediately(settings, storage, message, monkeypatch):
    started = asyncio.Event()

    async def download(url, directory, config, selection):
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr("cofesave.jobs.fetch", download)
    manager = JobManager(replace(settings, workers=1), storage)
    first = asyncio.create_task(manager.handle(message, LINK))
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        message.answer.assert_not_awaited()
        await asyncio.wait_for(manager.handle(message, LINK), timeout=2)
        assert "band" in message.answer.call_args.args[0]
    finally:
        await manager.stop()
    assert first.cancelled()
    assert manager.active_downloads == 0


async def test_cache_sends_without_downloading(settings, storage, message, monkeypatch):
    download = AsyncMock()
    monkeypatch.setattr("cofesave.jobs.fetch", download)
    storage.save(LINK.url, CachedVideo("file-123", "Some title"))
    manager = JobManager(settings, storage)
    manager.active_downloads = settings.workers
    await manager.handle(message, LINK)
    message.answer.assert_not_awaited()
    download.assert_not_awaited()
    assert message.answer_video.call_args.args[0] == "file-123"
    assert storage.stats()[2:] == (1, 1)


async def test_download_saved_and_temp_cleaned(settings, storage, message, monkeypatch):
    directories = []

    async def download(url, directory, config, selection):
        directories.append(directory)
        path = directory / "video.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "Test video")

    monkeypatch.setattr("cofesave.jobs.fetch", download)
    manager = JobManager(settings, storage)
    await manager.handle(message, LINK)
    message.answer.assert_not_awaited()
    assert storage.get(LINK.url).file_id == "telegram-file-123"
    assert storage.stats()[2:] == (1, 0)
    assert all(not directory.exists() for directory in directories)


async def test_stale_file_id_downloads_again(settings, storage, message, monkeypatch):
    async def download(url, directory, config, selection):
        path = directory / "video.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "new")

    monkeypatch.setattr("cofesave.jobs.fetch", download)
    storage.save(LINK.url, CachedVideo("old", "old"))
    message.answer_video.side_effect = [
        TelegramBadRequest(
            method=SendVideo(chat_id=1, video="old"), message="wrong file identifier"
        ),
        SimpleNamespace(video=SimpleNamespace(file_id="new")),
    ]
    manager = JobManager(settings, storage)
    await manager.handle(message, LINK)
    assert storage.get(LINK.url).file_id == "new"


async def test_failure_releases_download_slot_and_cleans_up(
    settings, storage, message, monkeypatch
):
    directories = []

    async def failing_download(url, directory, config, selection):
        directories.append(directory)
        (directory / "partial.mp4").write_bytes(b"partial")
        raise DownloadFailure("restricted")

    monkeypatch.setattr("cofesave.jobs.fetch", failing_download)
    manager = JobManager(settings, storage)
    await manager.handle(message, LINK)
    assert manager.active_downloads == 0
    assert not manager.tasks
    message.answer.assert_awaited_once()
    assert all(not directory.exists() for directory in directories)
    assert storage.stats()[2] == 0
    await manager.stop()


async def test_consecutive_requests_start_without_waiting(settings, storage, message, monkeypatch):
    both_started = asyncio.Event()
    release = asyncio.Event()
    started = 0

    async def download(url, directory, config, selection):
        nonlocal started
        started += 1
        if started == 2:
            both_started.set()
        await release.wait()
        path = directory / "video.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "video")

    monkeypatch.setattr("cofesave.jobs.fetch", download)
    other = SimpleNamespace(
        from_user=message.from_user,
        answer=AsyncMock(),
        answer_video=AsyncMock(
            return_value=SimpleNamespace(video=SimpleNamespace(file_id="cached"))
        ),
    )
    manager = JobManager(settings, storage)
    first = asyncio.create_task(manager.handle(message, LINK))
    second = asyncio.create_task(manager.handle(other, LINK))
    try:
        await asyncio.wait_for(both_started.wait(), timeout=2)
        release.set()
        await asyncio.wait_for(asyncio.gather(first, second), timeout=2)
    finally:
        await manager.stop()
    assert storage.stats()[2:] == (2, 0)


async def test_audio_and_video_qualities_use_separate_cache_entries(
    settings, storage, message, monkeypatch
):
    async def download(url, directory, config, selection):
        path = directory / f"video.{selection.extension}"
        path.write_bytes(b"media")
        return DownloadedVideo(path, "Test")

    fetch = AsyncMock(side_effect=download)
    monkeypatch.setattr("cofesave.jobs.fetch", fetch)
    message.answer_audio = AsyncMock(
        return_value=SimpleNamespace(audio=SimpleNamespace(file_id="audio-file"))
    )
    storage.save(LINK.url, CachedVideo("legacy-video", "Test"))
    manager = JobManager(settings, storage)

    await manager.handle(message, LINK, DownloadFormat.MP3)
    assert message.answer_audio.call_args.args[0].filename == "cofesave.mp3"
    await manager.handle(message, LINK, DownloadFormat.MP3)
    assert message.answer_audio.call_args.args[0] == "audio-file"
    await manager.handle(message, LINK, DownloadFormat.P360)
    await manager.handle(message, LINK, DownloadFormat.P720)

    assert [call.args[-1] for call in fetch.await_args_list] == [
        DownloadFormat.MP3,
        DownloadFormat.P360,
        DownloadFormat.P720,
    ]
    assert storage.get(LINK.url).file_id == "legacy-video"
