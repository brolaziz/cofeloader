import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendVideo

from cofesave.downloader import DownloadedVideo, DownloadFailure
from cofesave.jobs import Job, JobManager
from cofesave.links import parse_link
from cofesave.storage import CachedVideo

LINK = parse_link("https://youtu.be/dQw4w9WgXcQ")


async def test_one_pending_job_per_user(settings, storage, message):
    manager = JobManager(settings, storage)
    await manager.enqueue(message, LINK)
    await manager.enqueue(message, LINK)
    assert manager.queue.qsize() == 1
    assert "Oldingi" in message.answer.call_args.args[0]
    await manager.stop()


async def test_queue_bound_does_not_reserve_rejected_user(settings, storage, message):
    manager = JobManager(replace(settings, max_queue=1), storage)
    await manager.enqueue(message, LINK)
    other = SimpleNamespace(from_user=SimpleNamespace(id=2), answer=AsyncMock())
    await manager.enqueue(other, LINK)
    assert 2 not in manager.busy
    assert "to'lgan" in other.answer.call_args.args[0]
    await manager.stop()


async def test_status_failure_releases_reservation(settings, storage, message):
    import pytest

    manager = JobManager(settings, storage)
    message.answer.side_effect = RuntimeError("test")
    with pytest.raises(RuntimeError):
        await manager.enqueue(message, LINK)
    assert not manager.busy
    assert manager.queue.empty()


async def test_cooldown(settings, storage, message):
    manager = JobManager(settings, storage)
    await manager.enqueue(message, LINK)
    manager.busy.clear()  # Simulate completion before the cooldown expires.
    await manager.enqueue(message, LINK)
    assert manager.queue.qsize() == 1
    assert "biroz kuting" in message.answer.call_args.args[0]
    await manager.stop()


async def test_cache_sends_without_downloading(settings, storage, message, monkeypatch):
    download = AsyncMock()
    monkeypatch.setattr("cofesave.jobs.fetch", download)
    storage.save(LINK.url, CachedVideo("file-123", "Some title"))
    manager = JobManager(settings, storage)
    status = await message.answer("waiting")
    await manager.process(Job(message, status, LINK, 1))
    download.assert_not_awaited()
    assert message.answer_video.call_args.args[0] == "file-123"
    assert storage.stats()[2:] == (1, 1)


async def test_download_saved_and_temp_cleaned(settings, storage, message, monkeypatch):
    directories = []

    async def download(url, directory, config):
        directories.append(directory)
        path = directory / "video.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "Test video")

    monkeypatch.setattr("cofesave.jobs.fetch", download)
    manager = JobManager(settings, storage)
    await manager.process(Job(message, await message.answer("waiting"), LINK, 1))
    assert storage.get(LINK.url).file_id == "telegram-file-123"
    assert storage.stats()[2:] == (1, 0)
    assert all(not directory.exists() for directory in directories)


async def test_stale_file_id_downloads_again(settings, storage, message, monkeypatch):
    async def download(url, directory, config):
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
    await manager.process(Job(message, await message.answer("waiting"), LINK, 1))
    assert storage.get(LINK.url).file_id == "new"


async def test_failure_keeps_worker_alive_and_cleans_up(settings, storage, message, monkeypatch):
    directories = []

    async def failing_download(url, directory, config):
        directories.append(directory)
        (directory / "partial.mp4").write_bytes(b"partial")
        raise DownloadFailure("restricted")

    monkeypatch.setattr("cofesave.jobs.fetch", failing_download)
    manager = JobManager(settings, storage)
    manager.start()
    await manager.enqueue(message, LINK)
    await asyncio.wait_for(manager.queue.join(), timeout=2)
    assert not manager.busy
    assert all(not task.done() for task in manager.tasks)
    assert all(not directory.exists() for directory in directories)
    assert storage.stats()[2] == 0
    await manager.stop()


async def test_concurrent_identical_links_download_once(settings, storage, message, monkeypatch):
    count = 0

    async def download(url, directory, config):
        nonlocal count
        count += 1
        await asyncio.sleep(0.01)
        path = directory / "video.mp4"
        path.write_bytes(b"video")
        return DownloadedVideo(path, "video")

    monkeypatch.setattr("cofesave.jobs.fetch", download)
    other = SimpleNamespace(
        from_user=SimpleNamespace(id=2),
        answer=AsyncMock(return_value=await message.answer("")),
        answer_video=AsyncMock(
            return_value=SimpleNamespace(video=SimpleNamespace(file_id="cached"))
        ),
    )
    manager = JobManager(settings, storage)
    manager.start()
    await manager.enqueue(message, LINK)
    await manager.enqueue(other, LINK)
    await asyncio.wait_for(manager.queue.join(), timeout=2)
    assert count == 1
    assert storage.stats()[2:] == (2, 1)
    await manager.stop()
