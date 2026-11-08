import pytest

from cofesave.downloader import DownloadFailure, fetch


async def test_real_worker_process_rejects_non_platform_url(settings, tmp_path):
    # Runs the actual subprocess and JSON handshake, without contacting any website.
    with pytest.raises(DownloadFailure) as failure:
        await fetch("https://example.com/video", tmp_path, settings)
    assert failure.value.code == "unavailable"
    assert (tmp_path / "result.json").is_file()
