from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class Platform(str, Enum):
    YOUTUBE = "youtube"
    FACEBOOK = "facebook"
    TIKTOK = "tiktok"
    SOUNDCLOUD = "soundcloud"


class MediaKind(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    PLAYLIST = "playlist"
    ALBUM = "album"
    UNKNOWN = "unknown"


class DownloadBackend(str, Enum):
    YT_DLP = "yt_dlp"
    DIRECT = "direct"
    MEDIA_GROUP = "media_group"


class SendMethod(str, Enum):
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    MEDIA_GROUP = "media_group"


class ErrorCode(str, Enum):
    INVALID_URL = "invalid_url"
    EXTRACTOR_FAILED = "extractor_failed"
    PRIVATE_RESTRICTED = "private_restricted"
    AGE_LOGIN_REQUIRED = "age_login_required"
    DOWNLOAD_FAILED = "download_failed"
    CONVERSION_FAILED = "conversion_failed"
    UPLOAD_FAILED = "upload_failed"
    SESSION_EXPIRED = "session_expired"


class BotError(Exception):
    def __init__(self, code: ErrorCode, user_message: str, internal_message: str | None = None) -> None:
        super().__init__(internal_message or user_message)
        self.code = code
        self.user_message = user_message
        self.internal_message = internal_message or user_message


@dataclass(slots=True)
class PlaylistEntry:
    id: str
    title: str
    url: str
    duration: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlaylistEntry":
        return cls(
            id=str(data["id"]),
            title=str(data.get("title") or "Video không có tên"),
            url=str(data.get("url") or ""),
            duration=int(data["duration"]) if data.get("duration") is not None else None,
        )


@dataclass(slots=True)
class MediaInfo:
    provider: Platform
    source_url: str
    title: str
    full_caption: str | None = None
    uploader: str | None = None
    duration: int | None = None
    thumbnail: str | None = None
    view_count: int | None = None
    upload_date: str | None = None
    is_live: bool = False
    is_mix: bool = False
    is_playlist: bool = False
    media_kind: MediaKind = MediaKind.UNKNOWN
    total_count: int = 0
    available_actions: list[str] = field(default_factory=list)
    entries: list[PlaylistEntry] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["provider"] = self.provider.value
        data["media_kind"] = self.media_kind.value
        data["entries"] = [entry.to_dict() for entry in self.entries]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MediaInfo":
        return cls(
            provider=Platform(data["provider"]),
            source_url=str(data["source_url"]),
            title=str(data.get("title") or "Không có tiêu đề"),
            full_caption=data.get("full_caption"),
            uploader=data.get("uploader"),
            duration=int(data["duration"]) if data.get("duration") is not None else None,
            thumbnail=data.get("thumbnail"),
            view_count=int(data["view_count"]) if data.get("view_count") is not None else None,
            upload_date=data.get("upload_date"),
            is_live=bool(data.get("is_live", False)),
            is_mix=bool(data.get("is_mix", False)),
            is_playlist=bool(data.get("is_playlist", False)),
            media_kind=MediaKind(data.get("media_kind", MediaKind.UNKNOWN.value)),
            total_count=int(data.get("total_count", 0)),
            available_actions=list(data.get("available_actions", [])),
            entries=[PlaylistEntry.from_dict(entry) for entry in data.get("entries", [])],
            image_urls=list(data.get("image_urls", [])),
            extra=dict(data.get("extra", {})),
        )


@dataclass(slots=True)
class SessionData:
    job_id: str
    user_id: int
    provider: Platform
    source_url: str
    media_info: MediaInfo
    created_at: datetime
    expires_at: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "user_id": self.user_id,
            "provider": self.provider.value,
            "source_url": self.source_url,
            "media_info": self.media_info.to_dict(),
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SessionData":
        return cls(
            job_id=str(data["job_id"]),
            user_id=int(data["user_id"]),
            provider=Platform(data["provider"]),
            source_url=str(data["source_url"]),
            media_info=MediaInfo.from_dict(data["media_info"]),
            created_at=_parse_datetime(data["created_at"]),
            expires_at=_parse_datetime(data["expires_at"]),
        )


@dataclass(slots=True)
class DownloadPlan:
    action: str
    provider: Platform
    backend: DownloadBackend
    send_method: SendMethod
    source_url: str | None = None
    output_template: str | None = None
    output_path: Path | None = None
    converted_output_path: Path | None = None
    ydl_options: dict[str, Any] = field(default_factory=dict)
    cobalt_request: dict[str, Any] | None = None
    headers: dict[str, str] = field(default_factory=dict)
    fallback_urls: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)
    allowed_extensions: tuple[str, ...] = ()
    caption: str = ""
    filename_hint: str | None = None
    performer: str | None = None
    track_title: str | None = None
    duration: int | None = None
    supports_streaming: bool = False


@dataclass(slots=True)
class DownloadedItem:
    send_method: SendMethod
    caption: str
    file_path: Path | None = None
    file_size: int = 0
    filename_hint: str | None = None
    performer: str | None = None
    track_title: str | None = None
    duration: int | None = None
    supports_streaming: bool = False
    image_urls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CookieMetadata:
    user_id: int
    path: Path
    updated_at: datetime
    line_count: int


@dataclass(slots=True)
class StatsSnapshot:
    request_count: int
    item_processed_count: int
    success_count: int
    failure_count: int
    total_bytes: int
    unique_users: int


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed
