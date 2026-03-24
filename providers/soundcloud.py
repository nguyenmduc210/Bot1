from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yt_dlp

from models import BotError, DownloadBackend, DownloadPlan, ErrorCode, MediaInfo, MediaKind, Platform, PlaylistEntry, SendMethod, SessionData
from providers.base import BaseProvider
from providers.common import build_download_base_options, build_extract_options
from utils.formatters import ellipsize, escape_html, format_duration


class SoundCloudProvider(BaseProvider):
    @property
    def key(self) -> str:
        return Platform.SOUNDCLOUD.value

    def supports(self, url: str) -> bool:
        lowered = url.lower()
        return "soundcloud.com" in lowered or "on.soundcloud.com" in lowered

    async def extract_info(self, url: str, *, user_id: int) -> MediaInfo:
        del user_id
        try:
            info = await asyncio.to_thread(_extract_soundcloud_info_sync, url, self.settings.max_playlist_videos)
        except yt_dlp.utils.DownloadError as exc:
            raise BotError(ErrorCode.EXTRACTOR_FAILED, "Không thể lấy thông tin bài hát SoundCloud.") from exc
        if not info:
            raise BotError(ErrorCode.EXTRACTOR_FAILED, "Không thể lấy thông tin bài hát SoundCloud.")
        entries_raw = info.get("entries") or []
        if entries_raw:
            entries = []
            for entry in entries_raw:
                if not entry or not entry.get("id"):
                    continue
                entries.append(
                    PlaylistEntry(
                        id=str(entry["id"]),
                        title=entry.get("title") or "Track không có tên",
                        url=entry.get("url") or entry.get("webpage_url") or "",
                        duration=entry.get("duration"),
                    )
                )
            if not entries:
                raise BotError(ErrorCode.EXTRACTOR_FAILED, "Playlist SoundCloud không có track hợp lệ.")
            return MediaInfo(
                provider=Platform.SOUNDCLOUD,
                source_url=info.get("webpage_url", url),
                title=info.get("title") or "Playlist SoundCloud",
                uploader=info.get("uploader") or info.get("channel") or "Nghệ sĩ không rõ",
                thumbnail=info.get("thumbnail"),
                is_playlist=True,
                media_kind=MediaKind.PLAYLIST,
                total_count=int(info.get("playlist_count") or len(entries_raw)),
                available_actions=["scplmus"],
                entries=entries,
                extra={"fetched_count": len(entries)},
            )
        return MediaInfo(
            provider=Platform.SOUNDCLOUD,
            source_url=info.get("webpage_url", url),
            title=info.get("title") or "Bài hát SoundCloud",
            uploader=info.get("uploader") or "Nghệ sĩ không rõ",
            duration=info.get("duration"),
            thumbnail=info.get("thumbnail"),
            media_kind=MediaKind.AUDIO,
            available_actions=["scmus"],
        )

    def build_download_options(
        self,
        *,
        action: str,
        session: SessionData,
        output_dir: Path,
        item_index: int | None = None,
    ) -> DownloadPlan:
        output_dir.mkdir(parents=True, exist_ok=True)
        media = session.media_info
        source_url = session.source_url
        title = media.title
        duration = media.duration
        if action == "scplmus":
            if item_index is None:
                raise ValueError("SoundCloud playlist action requires item_index")
            entry = media.entries[item_index]
            source_url = entry.url
            title = entry.title
            duration = entry.duration
        options = build_download_base_options(output_dir=output_dir)
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [],
            }
        )
        return DownloadPlan(
            action=action,
            provider=Platform.SOUNDCLOUD,
            backend=DownloadBackend.YT_DLP,
            send_method=SendMethod.AUDIO,
            source_url=source_url,
            output_template=options["outtmpl"],
            ydl_options=options,
            allowed_extensions=(".mp3", ".m4a", ".webm", ".opus", ".ogg", ".aac", ".wav", ".flac"),
            caption=(
                f"🎵 <b>{escape_html(ellipsize(title, 80))}</b>\n"
                f"👤 {escape_html(media.uploader or 'Không rõ')}\n"
                f"🎚️ Âm thanh gốc · {escape_html(format_duration(duration))}"
            ),
            performer=media.uploader,
            track_title=ellipsize(title, 64),
            duration=duration,
        )


def _extract_soundcloud_info_sync(url: str, max_videos: int) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(build_extract_options(playlist_end=max_videos)) as ydl:
        return ydl.extract_info(url, download=False)
