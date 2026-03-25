from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import yt_dlp

from models import BotError, DownloadBackend, DownloadPlan, ErrorCode, MediaInfo, MediaKind, Platform, SendMethod, SessionData
from providers.base import BaseProvider
from providers.common import best_thumbnail, build_download_base_options, build_extract_options
from utils.files import sanitize_filename
from utils.formatters import ellipsize, escape_html, format_duration


_FB_DOMAINS = (
    "facebook.com",
    "fb.com",
    "fb.watch",
    "m.facebook.com",
    "www.facebook.com",
)


class FacebookProvider(BaseProvider):
    @property
    def key(self) -> str:
        return Platform.FACEBOOK.value

    def supports(self, url: str) -> bool:
        lowered = url.lower()
        return any(domain in lowered for domain in _FB_DOMAINS)

    async def extract_info(self, url: str, *, user_id: int) -> MediaInfo:
        try:
            info = await asyncio.to_thread(_extract_facebook_info_sync, url, self._cookie_path())
        except yt_dlp.utils.DownloadError as exc:
            raise _map_facebook_error(exc) from exc
        if not info:
            raise BotError(ErrorCode.EXTRACTOR_FAILED, "Không thể lấy thông tin nội dung Facebook.")
        if info.get("is_live"):
            raise BotError(ErrorCode.EXTRACTOR_FAILED, "Bot chưa hỗ trợ livestream Facebook đang diễn ra.")
        return MediaInfo(
            provider=Platform.FACEBOOK,
            source_url=info.get("webpage_url", url),
            title=info.get("title") or info.get("description", "")[:80] or "Nội dung Facebook",
            full_caption=info.get("description") or info.get("title"),
            uploader=info.get("uploader") or info.get("channel") or "Không rõ",
            duration=info.get("duration"),
            thumbnail=best_thumbnail(info),
            view_count=info.get("view_count"),
            upload_date=info.get("upload_date"),
            is_live=bool(info.get("is_live")),
            media_kind=MediaKind.VIDEO,
            available_actions=["fbv", "fba", "fbdoc"],
        )

    def build_download_options(
        self,
        *,
        action: str,
        session: SessionData,
        output_dir: Path,
        item_index: int | None = None,
    ) -> DownloadPlan:
        del item_index
        output_dir.mkdir(parents=True, exist_ok=True)
        media = session.media_info
        title = media.title
        options = build_download_base_options(output_dir=output_dir, cookiefile=self._cookie_path())
        filename_base = sanitize_filename(title)
        caption_prefix = "📁" if action == "fbdoc" else ("🎵" if action == "fba" else "📹")
        caption = (
            f"{caption_prefix} <b>{escape_html(ellipsize(title, 80))}</b>\n"
            f"👤 {escape_html(media.uploader or 'Không rõ')}\n"
            f"⏱️ {escape_html(format_duration(media.duration))}"
        )
        if action in {"fbv", "fbdoc"}:
            options.update(
                {
                    "format": (
                        "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
                        "/bestvideo[height<=1080]+bestaudio"
                        "/best[height<=1080]"
                        "/best"
                    ),
                    "merge_output_format": "mp4",
                }
            )
            return DownloadPlan(
                action=action,
                provider=Platform.FACEBOOK,
                backend=DownloadBackend.YT_DLP,
                send_method=SendMethod.DOCUMENT if action == "fbdoc" else SendMethod.VIDEO,
                source_url=session.source_url,
                output_template=options["outtmpl"],
                ydl_options=options,
                allowed_extensions=(".mp4", ".mkv", ".webm"),
                caption=caption,
                filename_hint=f"{filename_base}.mp4" if action == "fbdoc" else None,
                duration=media.duration,
                supports_streaming=action == "fbv",
            )

        options.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "320",
                    },
                    {"key": "FFmpegMetadata", "add_metadata": True},
                ],
            }
        )
        return DownloadPlan(
            action=action,
            provider=Platform.FACEBOOK,
            backend=DownloadBackend.YT_DLP,
            send_method=SendMethod.AUDIO,
            source_url=session.source_url,
            output_template=options["outtmpl"],
            ydl_options=options,
            allowed_extensions=(".mp3", ".m4a", ".webm"),
            caption=caption.replace("📹", "🎵"),
            performer=media.uploader,
            track_title=ellipsize(title, 64),
            duration=media.duration,
        )

    def _cookie_path(self) -> Path | None:
        cookie = self.settings.facebook_cookie_file
        if cookie and cookie.is_file():
            return cookie
        return None


def _extract_facebook_info_sync(url: str, cookiefile: Path | None) -> dict[str, Any]:
    options = build_extract_options(cookiefile=cookiefile)
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def _map_facebook_error(exc: Exception) -> BotError:
    message = str(exc).lower()
    if any(keyword in message for keyword in ("private", "login", "403", "404")):
        return BotError(
            ErrorCode.PRIVATE_RESTRICTED,
            "Nội dung Facebook này đang riêng tư hoặc yêu cầu đăng nhập.",
        )
    return BotError(
        ErrorCode.EXTRACTOR_FAILED,
        "Không thể phân tích liên kết Facebook này.",
    )
