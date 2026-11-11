"""Isolated downloader process. Never receives the Telegram token."""

import argparse
import json
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from cofesave.formats import DownloadFormat
from cofesave.links import parse_link


class QuietLogger:
    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def options(directory: Path, max_bytes: int, max_duration: int, cookies: str | None) -> dict:
    def match_filter(info: dict, *, incomplete: bool = False) -> str | None:
        if info.get("is_live") or info.get("live_status") == "is_live":
            return "COFE_LIVE"
        if max_duration and (info.get("duration") or 0) > max_duration:
            return "COFE_DURATION"
        if (info.get("filesize") or 0) > max_bytes:
            return "COFE_SIZE"
        return None

    def progress(data: dict) -> None:
        if data.get("downloaded_bytes", 0) > max_bytes:
            raise DownloadError("COFE_SIZE")

    # Prefer H.264 MP4 + AAC, falling back to a combined MP4 with audio.
    # Size filters help select smaller formats; the parent also enforces disk and time limits.
    video = f"[height<=?720][filesize_approx<=?{max_bytes}]"
    return {
        "format": (
            f"bv[ext=mp4][vcodec^=avc1]{video}+ba[ext=m4a]/"
            f"b[ext=mp4][vcodec^=avc1]{video}/b[ext=mp4]{video}"
        ),
        "outtmpl": str(directory / "video.%(ext)s"),
        "merge_output_format": "mp4",
        "noplaylist": True,
        "playlist_items": "1",
        "max_filesize": max_bytes,
        "match_filter": match_filter,
        "progress_hooks": [progress],
        "socket_timeout": 20,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 1,
        "concurrent_fragment_downloads": 1,
        "quiet": True,
        "no_warnings": True,
        "logger": QuietLogger(),
        "cachedir": False,
        "cookiefile": cookies,
        "overwrites": False,
        "allowed_extractors": ["youtube.*", "instagram.*", "tiktok.*", r"vm\.tiktok"],
        "js_runtimes": {"node": {}},
    }


def error_code(message: str) -> str:
    lower = message.lower()
    if "cofe_duration" in lower:
        return "duration"
    if "cofe_live" in lower:
        return "live"
    if "cofe_size" in lower or "larger than max" in lower:
        return "size"
    if any(word in lower for word in ("timed out", "timeout")):
        return "timeout"
    if "not a bot" in lower or "http error 429" in lower:
        return "platform_blocked"
    if any(word in lower for word in ("sign in", "login", "private", "cookies")):
        return "restricted"
    if "requested format is not available" in lower:
        return "format"
    return "unavailable"


def fits_resolution(media_format: dict, limit: int) -> bool:
    if media_format.get("vcodec") == "none":
        return True
    dimensions = (media_format.get("height") or 0, media_format.get("width") or 0)
    # For a vertical video the shorter dimension is its width.
    return any(0 < dimension <= limit for dimension in dimensions)


def download(
    url: str,
    directory: Path,
    max_bytes: int,
    duration: int,
    cookies: str | None,
    selection: DownloadFormat = DownloadFormat.AUTO,
) -> dict:
    link = parse_link(url)
    config = options(directory, max_bytes, duration, cookies)
    size = f"[filesize<=?{max_bytes}][filesize_approx<=?{max_bytes}]"
    if link.platform == "TikTok":
        config["socket_timeout"] = 10
        config["extractor_retries"] = 0
        if selection is DownloadFormat.AUTO:
            config["format"] = f"b[ext=mp4]{size}/{config['format']}"
    if selection is DownloadFormat.MP3:
        config["format"] = f"ba{size}/b{size}"
        config["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "128"}
        ]
    resolution = selection.resolution
    if resolution is not None:
        config["format"] = (
            f"bv*[ext=mp4][vcodec^=avc1]{size}+ba[ext=m4a]{size}/b[ext=mp4]{size}"
        )
        config["format_sort"] = ["res"]
    with YoutubeDL(config) as downloader:
        if resolution is not None:
            selector = downloader.format_selector

            def select_video(context):
                formats = [fmt for fmt in context["formats"] if fits_resolution(fmt, resolution)]
                return selector({**context, "formats": formats})

            downloader.format_selector = select_video
        info = downloader.extract_info(link.url, download=True)
    if not info:
        return {"error": "unavailable"}
    if info.get("_type") in {"playlist", "multi_video"}:
        entries = [entry for entry in info.get("entries", []) if entry]
        if not entries:
            return {"error": "unavailable"}
        info = entries[0]
    path = directory / f"video.{selection.extension}"
    if not path.is_file() or path.stat().st_size == 0:
        reason = config["match_filter"](info)
        return {"error": error_code(reason or "")}
    if path.stat().st_size > max_bytes:
        return {"error": "size"}
    result = {"filename": path.name, "title": str(info.get("title") or "Video")[:180]}
    if link.platform == "TikTok" and isinstance(info.get("id"), str):
        result["tiktok_id"] = info["id"]
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("directory", type=Path)
    parser.add_argument("max_bytes", type=int)
    parser.add_argument("max_duration", type=int)
    parser.add_argument("--cookies")
    parser.add_argument("--format", type=DownloadFormat, default=DownloadFormat.AUTO)
    args = parser.parse_args()
    try:
        result = download(
            args.url, args.directory, args.max_bytes, args.max_duration, args.cookies, args.format
        )
    except Exception as error:
        # Do not expose extractor errors, URLs, or cookie data to logs/users.
        result = {"error": error_code(str(error))}
    (args.directory / "result.json").write_text(json.dumps(result), encoding="utf-8")


if __name__ == "__main__":
    main()
