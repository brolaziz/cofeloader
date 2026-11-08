import pytest

from cofesave.links import LinkError, parse_link


@pytest.mark.parametrize(
    "url",
    [
        "https://youtu.be/dQw4w9WgXcQ?si=tracking",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=ignored",
        "https://m.youtube.com/shorts/dQw4w9WgXcQ",
        "https://youtube.com/embed/dQw4w9WgXcQ",
    ],
)
def test_youtube_canonicalization(url):
    link = parse_link(f"Shu video: {url}")
    assert link.platform == "YouTube"
    assert link.url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


@pytest.mark.parametrize("path", ["reel/ABC_123", "reels/ABC_123", "p/ABC_123"])
def test_instagram_removes_tracking(path):
    link = parse_link(f"https://instagram.com/{path}/?igsh=tracking")
    assert "?" not in link.url
    assert link.platform == "Instagram"
    assert "/reels/" not in link.url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@someone/video/123456789",
        "https://vm.tiktok.com/ABC123/",
        "https://vt.tiktok.com/ABC123/",
        "https://www.tiktok.com/t/ABC123/",
    ],
)
def test_tiktok_links(url):
    assert parse_link(url).platform == "TikTok"


@pytest.mark.parametrize(
    "url",
    [
        "hello",
        "https://127.0.0.1/video",
        "http://169.254.169.254/latest/meta-data",
        "https://youtube.com.attacker.test/watch?v=dQw4w9WgXcQ",
        "https://youtube.com@evil.test/watch?v=dQw4w9WgXcQ",
        "https://user:password@youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com:8000/watch?v=dQw4w9WgXcQ",
        "https://youtube.com:bad/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/playlist?list=test",
        "https://youtube.com/@channel",
        "https://youtu.be/invalid",
        "https://instagram.com/username/",
        "https://instagram.com/stories/user/123",
        "https://tiktok.com/@someone",
        "https://vm.tiktok.com/",
        "https://www.tiktok.com/@someone/photo/123",
        "https://youtu.be/dQw4w9WgXcQ https://instagram.com/p/ABC/",
    ],
)
def test_rejects_unsupported_and_unsafe_links(url):
    with pytest.raises(LinkError):
        parse_link(url)
