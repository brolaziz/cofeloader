import pytest
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from cofesave.links import parse_link
from cofesave.worker import download, error_code, options


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


@pytest.mark.parametrize(
    "url",
    [
        "https://vt.tiktok.com/ZExample/",
        "https://vm.tiktok.com/ZExample/",
        "https://m.tiktok.com/t/ZExample/",
        "https://tiktok.com/@creator/video/7663144858546277655",
        "https://m.tiktok.com/@creator/video/7663144858546277655",
    ],
)
def test_tiktok_links_match_an_enabled_extractor(url, tmp_path):
    canonical = parse_link(url).url
    with YoutubeDL(options(tmp_path, 48_000_000, 0, None)) as downloader:
        assert any(extractor.suitable(canonical) for extractor in downloader._ies.values())


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
    "url",
    [
        "https://www.instagram.com/reel/Example/",
        "https://www.tiktok.com/@creator/video/7663144858546277655",
    ],
)
@pytest.mark.parametrize("max_bytes", [100, 50])
def test_native_download_chooses_highest_quality_and_keeps_extension(
    url, max_bytes, tmp_path, monkeypatch
):
    def extract_info(self, url, *, download):
        assert "merge_output_format" not in self.params
        result = self.process_ie_result(
            {
                "id": "123",
                "title": "Example",
                "webpage_url": url,
                "formats": [
                    {
                        "format_id": "mp4",
                        "url": "https://example.com/low.mp4",
                        "ext": "mp4",
                        "vcodec": "avc1",
                        "acodec": "aac",
                        "height": 720,
                        "width": 1280,
                        "filesize": 40,
                        "preference": 2,
                    },
                    {
                        "format_id": "webm",
                        "url": "https://example.com/high.webm",
                        "ext": "webm",
                        "vcodec": "vp9",
                        "acodec": "opus",
                        "height": 2160,
                        "width": 3840,
                        "filesize": 80,
                    },
                    {
                        "format_id": "bytevc2",
                        "url": "https://example.com/unplayable.mp4",
                        "ext": "mp4",
                        "vcodec": "bytevc2",
                        "acodec": "aac",
                        "height": 4320,
                        "width": 7680,
                    },
                ],
            },
            download=False,
        )
        assert result["format_id"] == "webm"
        if result["filesize"] <= max_bytes:
            (tmp_path / f"video.{result['ext']}").write_bytes(b"original")
        return result

    monkeypatch.setattr(YoutubeDL, "extract_info", extract_info)
    result = download(url, tmp_path, max_bytes, 1200, None)
    if max_bytes == 50:
        assert result == {"error": "size"}
    else:
        assert result["filename"] == "video.webm"


@pytest.mark.parametrize(
    "text,code",
    [
        ("COFE_DURATION", "duration"),
        ("COFE_SIZE", "size"),
        ("COFE_LIVE", "live"),
        ("Sign in to confirm you're not a bot", "platform_blocked"),
        ("HTTP Error 429: Too Many Requests", "platform_blocked"),
        ("Requested format is not available", "format"),
        ("Private video", "restricted"),
        ("Unable to download webpage: read timed out", "timeout"),
        ("unknown error with sensitive URL", "unavailable"),
    ],
)
def test_safe_error_mapping(text, code):
    assert error_code(text) == code
