from __future__ import annotations

import asyncio
from pathlib import Path

from models import BotError, DownloadBackend, DownloadPlan, ErrorCode, MediaInfo, MediaKind, Platform, SendMethod, SessionData
from providers.base import BaseProvider
from providers.common import build_download_base_options
from utils.files import sanitize_filename
from utils.formatters import ellipsize, escape_html


class TikTokProvider(BaseProvider):
    @property
    def key(self) -> str:
        return Platform.TIKTOK.value

    def supports(self, url: str) -> bool:
        lowered = url.lower()
        return "tiktok.com" in lowered or "vt.tiktok.com" in lowered

    async def extract_info(self, url: str, *, user_id: int) -> MediaInfo:
        del user_id
        data = await self._extract_tiktok_data(url)
        if not data:
            raise BotError(
                ErrorCode.EXTRACTOR_FAILED,
                "Không thể lấy thông tin nội dung TikTok lúc này.",
            )

        image_urls = list(data.get("images") or [])
        is_album = bool(image_urls)
        actions = ["img"] if is_album else ["vid", "mus", "tkdoc"]
        return MediaInfo(
            provider=Platform.TIKTOK,
            source_url=url,
            title=data.get("title") or "Nội dung TikTok",
            thumbnail=(image_urls[0] if image_urls else data.get("cover")),
            media_kind=MediaKind.ALBUM if is_album else MediaKind.VIDEO,
            available_actions=actions,
            image_urls=image_urls,
            extra={
                "id": data.get("id"),
                "play": data.get("play"),
                "music": data.get("music"),
                "cover": data.get("cover"),
                "source_name": data.get("source_name"),
                "original_url": url,
            },
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
        filename_base = sanitize_filename(media.title)
        caption_title = escape_html(ellipsize(media.title, 80))
        if action == "img":
            return DownloadPlan(
                action=action,
                provider=Platform.TIKTOK,
                backend=DownloadBackend.MEDIA_GROUP,
                send_method=SendMethod.MEDIA_GROUP,
                image_urls=media.image_urls,
                caption=f"📸 <b>{caption_title}</b>",
            )

        if action == "tkdoc":
            options = build_download_base_options(output_dir=output_dir)
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
                provider=Platform.TIKTOK,
                backend=DownloadBackend.YT_DLP,
                send_method=SendMethod.DOCUMENT,
                source_url=str(media.extra.get("original_url") or session.source_url),
                output_template=options["outtmpl"],
                ydl_options=options,
                allowed_extensions=(".mp4", ".mkv", ".webm"),
                caption=f"📁 <b>{caption_title}</b>\n🎬 TikTok · MP4 1080p · File gốc",
                filename_hint=f"{filename_base}.mp4",
            )

        if action == "mus":
            source_url = str(media.extra.get("play") or "")
            if not source_url:
                raise BotError(
                    ErrorCode.DOWNLOAD_FAILED,
                    "TikTok không trả về file video hợp lệ để tách âm thanh.",
                )
            return DownloadPlan(
                action=action,
                provider=Platform.TIKTOK,
                backend=DownloadBackend.DIRECT,
                send_method=SendMethod.AUDIO,
                source_url=source_url,
                output_path=output_dir / "media.mp4",
                converted_output_path=output_dir / "media.m4a",
                headers={
                    "Referer": "https://www.tiktok.com/",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                },
                allowed_extensions=(".m4a", ".mp3"),
                caption=f"🎵 <b>{caption_title}</b>\n🎚️ Âm thanh gốc từ video",
                filename_hint=f"{filename_base}.m4a",
                track_title=ellipsize(media.title, 64),
            )

        source_url = media.extra.get("play")
        if not source_url:
            raise BotError(
                ErrorCode.DOWNLOAD_FAILED,
                "TikTok không trả về đường dẫn video hợp lệ cho nội dung này.",
            )
        output_path = output_dir / "media.mp4"
        fallback_urls = []
        video_id = media.extra.get("id")
        if video_id and video_id != "fallback_id":
            fallback_urls.append(f"https://www.tikwm.com/video/media/play/{video_id}.mp4")
        return DownloadPlan(
            action=action,
            provider=Platform.TIKTOK,
            backend=DownloadBackend.DIRECT,
            send_method=SendMethod.VIDEO,
            source_url=str(source_url),
            output_path=output_path,
            headers={
                "Referer": "https://www.tiktok.com/",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            },
            fallback_urls=fallback_urls,
            allowed_extensions=(".mp4",),
            caption=f"🎬 <b>{caption_title}</b>",
            filename_hint=f"{filename_base}.mp4",
            track_title=ellipsize(media.title, 64),
            supports_streaming=True,
        )

    async def _extract_tiktok_data(self, url: str) -> dict | None:
        primary = await self._extract_from_primary(url)
        if primary:
            return primary
        return await self._extract_from_fallback(url)

    async def _extract_from_primary(self, url: str) -> dict | None:
        for _ in range(2):
            try:
                payload = await self.http_client.get_json(
                    self.settings.tiktok_primary_api,
                    params={"url": url, "hd": 1},
                    timeout_seconds=self.settings.http_timeout_seconds,
                )
                if payload.get("code") != 0:
                    continue
                data = payload.get("data") or {}
                if data.get("play") or data.get("images"):
                    return {
                        "id": data.get("id"),
                        "title": data.get("title") or "Không có tiêu đề",
                        "cover": data.get("cover"),
                        "play": data.get("play"),
                        "music": data.get("music"),
                        "images": data.get("images") or [],
                        "source_name": "🟢 TikWM",
                    }
            except Exception:
                await asyncio.sleep(self.settings.http_backoff_seconds)
        return None

    async def _extract_from_fallback(self, url: str) -> dict | None:
        try:
            payload = await self.http_client.get_json(
                self.settings.tiktok_fallback_api,
                params={"url": url, "minimal": "false"},
                timeout_seconds=self.settings.http_timeout_seconds,
            )
        except Exception:
            return None
        data = payload.get("data", payload)
        images = data.get("image_data", {}).get("no_watermark_image_list", []) or data.get("images", [])
        video_node = data.get("video_data") or data.get("video")
        play_url = None
        if isinstance(video_node, list) and video_node:
            play_url = video_node[0]
        elif isinstance(video_node, dict):
            play_url = (
                video_node.get("nwm_video_url_HQ")
                or video_node.get("nwm_video_url")
                or (video_node.get("play_addr") or {}).get("url_list", [None])[0]
            )
        music_node = data.get("music") or data.get("music_info") or {}
        music_url = None
        if isinstance(music_node, dict):
            play_node = music_node.get("play_url") or {}
            if isinstance(play_node, dict):
                music_url = play_node.get("url_list", [None])[0] or play_node.get("uri")
            elif isinstance(play_node, str):
                music_url = play_node
            music_url = music_url or music_node.get("play")
        cover = data.get("cover")
        if images:
            cover = images[0]
        if play_url or images:
            return {
                "id": "fallback_id",
                "title": data.get("desc") or data.get("title") or "Không có tiêu đề",
                "cover": cover,
                "play": play_url,
                "music": music_url or data.get("music_url"),
                "images": images,
                "source_name": "🟡 API Dự phòng",
            }
        return None
