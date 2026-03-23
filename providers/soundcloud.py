from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yt_dlp

from models import BotError, DownloadBackend, DownloadPlan, ErrorCode, MediaInfo, MediaKind, Platform, SendMethod, SessionData
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
            info = await asyncio.to_thread(_extract_soundcloud_info_sync, url)
        except yt_dlp.utils.DownloadError as exc:
            raise BotError(ErrorCode.EXTRACTOR_FAILED, "Không thể lấy thông tin bài hát SoundCloud.") from exc
        if not info:
            raise BotError(ErrorCode.EXTRACTOR_FAILED, "Không thể lấy thông tin bài hát SoundCloud.")
        return MediaInfo(
            provider=Platform.SOUNDCLOUD,
            source_url=url,
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
        del action, item_index
        output_dir.mkdir(parents=True, exist_ok=True)
        media = session.media_info
        options = build_download_base_options(output_dir=output_dir)
        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "320",
                    }
                ],
            }
        )
        return DownloadPlan(
            action="scmus",
            provider=Platform.SOUNDCLOUD,
            backend=DownloadBackend.YT_DLP,
            send_method=SendMethod.AUDIO,
            source_url=session.source_url,
            output_template=options["outtmpl"],
            ydl_options=options,
            allowed_extensions=(".mp3", ".m4a", ".webm"),
            caption=(
                f"🎵 <b>{escape_html(ellipsize(media.title, 80))}</b>\n"
                f"👤 {escape_html(media.uploader or 'Không rõ')}\n"
                f"🎚️ MP3 320kbps · {escape_html(format_duration(media.duration))}"
            ),
            performer=media.uploader,
            track_title=ellipsize(media.title, 64),
            duration=media.duration,
        )


def _extract_soundcloud_info_sync(url: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL(build_extract_options()) as ydl:
        return ydl.extract_info(url, download=False)
