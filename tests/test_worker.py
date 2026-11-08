import pytest
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from cofesave.worker import error_code, options


def test_live_duration_and_size_guards(tmp_path):
    config = options(tmp_path, 100, 60, None)
    check = config["match_filter"]
    assert check({"is_live": True}) == "COFE_LIVE"
    assert check({"duration": 61}) == "COFE_DURATION"
    assert check({"filesize": 101}) == "COFE_SIZE"
    assert check({"duration": 60, "filesize": 100}) is None
    with pytest.raises(DownloadError):
        config["progress_hooks"][0]({"downloaded_bytes": 101})


def test_platform_extractors_enabled_generic_disabled(tmp_path):
    with YoutubeDL(options(tmp_path, 48_000_000, 1200, None)) as downloader:
        keys = {extractor.ie_key().lower() for extractor in downloader._ies.values()}
    assert "youtube" in keys
    assert "instagram" in keys
    assert "tiktok" in keys
    assert "generic" not in keys


def test_format_selection_accepts_unknown_sizes(tmp_path):
    # Instagram/TikTok often omit height/filesize estimates.
    with YoutubeDL(options(tmp_path, 48_000_000, 1200, None)) as downloader:
        result = downloader.process_ie_result(
            {
                "id": "test",
                "title": "test",
                "webpage_url": "https://example.com/test",
                "formats": [
                    {
                        "format_id": "mp4",
                        "url": "https://example.com/test.mp4",
                        "ext": "mp4",
                        "vcodec": "avc1",
                        "acodec": "mp4a",
                    }
                ],
            },
            download=False,
        )
    assert result["format_id"] == "mp4"


@pytest.mark.parametrize(
    "text,code",
    [
        ("COFE_DURATION", "duration"),
        ("COFE_SIZE", "size"),
        ("COFE_LIVE", "live"),
        ("Sign in to confirm you're not a bot", "restricted"),
        ("Private video", "restricted"),
        ("unknown error with sensitive URL", "unavailable"),
    ],
)
def test_safe_error_mapping(text, code):
    assert error_code(text) == code
