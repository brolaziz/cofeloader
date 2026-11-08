import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

URL_PATTERN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
DOMAINS = {
    "youtube.com": "YouTube",
    "www.youtube.com": "YouTube",
    "m.youtube.com": "YouTube",
    "music.youtube.com": "YouTube",
    "youtu.be": "YouTube",
    "instagram.com": "Instagram",
    "www.instagram.com": "Instagram",
    "tiktok.com": "TikTok",
    "www.tiktok.com": "TikTok",
    "m.tiktok.com": "TikTok",
    "vm.tiktok.com": "TikTok",
    "vt.tiktok.com": "TikTok",
}


class LinkError(ValueError):
    pass


@dataclass(frozen=True)
class VideoLink:
    url: str
    platform: str


def parse_link(text: str) -> VideoLink:
    urls = URL_PATTERN.findall(text)
    if len(urls) != 1:
        raise LinkError("Bitta YouTube, Instagram yoki TikTok video havolasini yuboring.")
    raw = urls[0].rstrip(".,!;:)]}")
    try:
        parts = urlsplit(raw)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError as error:
        raise LinkError("Havola formati noto'g'ri.") from error
    if host not in DOMAINS or parts.username or parts.password or port not in (None, 443):
        raise LinkError("Faqat YouTube, Instagram va TikTok havolalari qo'llab-quvvatlanadi.")
    platform = DOMAINS[host]
    path = parts.path.rstrip("/")
    if platform == "YouTube":
        if host == "youtu.be":
            video_id = path.lstrip("/")
        elif path == "/watch":
            video_id = parse_qs(parts.query).get("v", [""])[0]
        elif re.fullmatch(r"/(shorts|embed)/[A-Za-z0-9_-]{11}", path):
            video_id = path.rsplit("/", 1)[1]
        else:
            video_id = ""
        if not VIDEO_ID.fullmatch(video_id):
            raise LinkError("YouTube kanal yoki pleylist emas, bitta video havolasini yuboring.")
        return VideoLink(f"https://www.youtube.com/watch?v={video_id}", platform)
    if platform == "Instagram":
        match = re.fullmatch(r"/(reel|reels|p|tv)/([A-Za-z0-9_-]+)", path)
        if not match:
            raise LinkError("Instagram Reel yoki video post havolasini yuboring.")
        kind = "reel" if match[1] == "reels" else match[1]
        return VideoLink(f"https://www.instagram.com/{kind}/{match[2]}/", platform)
    if host in {"vm.tiktok.com", "vt.tiktok.com"}:
        if not re.fullmatch(r"/[A-Za-z0-9]+", path):
            raise LinkError("TikTok video havolasi noto'g'ri.")
    elif not (re.fullmatch(r"/@[^/]+/video/\d+", path) or re.fullmatch(r"/t/[A-Za-z0-9]+", path)):
        raise LinkError("TikTok profil emas, video havolasini yuboring.")
    return VideoLink(f"https://{host}{path}/", platform)
