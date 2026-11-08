import asyncio
import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from cofesave.downloader import DownloadFailure, fetch


async def test_valid_result_and_token_not_in_child_environment(settings, tmp_path, monkeypatch):
    path = tmp_path / "video.mp4"
    path.write_bytes(b"video")
    (tmp_path / "result.json").write_text(json.dumps({"filename": path.name, "title": "Video"}))
    process = SimpleNamespace(returncode=0, wait=AsyncMock(return_value=0))
    factory = AsyncMock(return_value=process)
    monkeypatch.setattr("cofesave.downloader.asyncio.create_subprocess_exec", factory)
    monkeypatch.setattr("cofesave.downloader.stop_process", AsyncMock())
    monkeypatch.setenv("BOT_TOKEN", "secret-token")
    video = await fetch("https://youtu.be/dQw4w9WgXcQ", tmp_path, settings)
    assert video.path == path.resolve()
    assert "BOT_TOKEN" not in factory.call_args.kwargs["env"]
    assert "secret-token" not in factory.call_args.args


async def test_timeout_stops_child(settings, tmp_path, monkeypatch):
    async def waiting():
        await asyncio.Event().wait()

    process = SimpleNamespace(returncode=None, wait=waiting)
    stop = AsyncMock()
    monkeypatch.setattr(
        "cofesave.downloader.asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr("cofesave.downloader.stop_process", stop)
    with pytest.raises(DownloadFailure) as failure:
        await fetch("url", tmp_path, replace(settings, download_timeout=0.01))
    assert failure.value.code == "timeout"
    stop.assert_awaited_once_with(process)


async def test_cancellation_stops_child(settings, tmp_path, monkeypatch):
    started = asyncio.Event()

    async def waiting():
        started.set()
        await asyncio.Event().wait()

    process = SimpleNamespace(returncode=None, wait=waiting)
    stop = AsyncMock()
    monkeypatch.setattr(
        "cofesave.downloader.asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr("cofesave.downloader.stop_process", stop)
    task = asyncio.create_task(fetch("url", tmp_path, settings))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    stop.assert_awaited_once_with(process)


@pytest.mark.parametrize(
    "result,expected",
    [
        ({"error": "restricted"}, "restricted"),
        ({"filename": "../outside.mp4", "title": "x"}, "unavailable"),
        ({"filename": "video.mp4", "title": "x"}, "size"),
    ],
)
async def test_rejects_worker_errors_traversal_and_oversize(
    result, expected, settings, tmp_path, monkeypatch
):
    (tmp_path / "video.mp4").write_bytes(b"oversized video")
    (tmp_path / "result.json").write_text(json.dumps(result))
    process = SimpleNamespace(returncode=0, wait=AsyncMock())
    monkeypatch.setattr(
        "cofesave.downloader.asyncio.create_subprocess_exec", AsyncMock(return_value=process)
    )
    monkeypatch.setattr("cofesave.downloader.stop_process", AsyncMock())
    with pytest.raises(DownloadFailure) as failure:
        await fetch("url", tmp_path, replace(settings, max_bytes=2))
    assert failure.value.code == expected
