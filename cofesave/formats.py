from enum import StrEnum


class DownloadFormat(StrEnum):
    AUTO = "auto"
    MP3 = "mp3"
    P360 = "360"
    P720 = "720"
    P1080 = "1080"

    @property
    def extension(self) -> str:
        return "mp3" if self is self.MP3 else "mp4"

    @property
    def resolution(self) -> int | None:
        return int(self) if self.isdecimal() else None

    def cache_key(self, key: str, platform: str) -> str:
        if self is self.MP3:
            return f"{self}:{key}"
        if self is self.AUTO and platform != "YouTube":
            key = f"original:{key}"
        elif self is not self.AUTO:
            key = f"{self}:{key}"
        # Older file IDs may refer to square copies or omit display dimensions.
        return f"video:v2:{key}"
