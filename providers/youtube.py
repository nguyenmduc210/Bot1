from __future__ import annotations

import asyncio
import logging
import re
import urllib.parse
from pathlib import Path
from typing import Any

import yt_dlp

from logging_setup import log_extra
from models import BotError, DownloadBackend, DownloadPlan, ErrorCode, MediaInfo, MediaKind, Platform, PlaylistEntry, SendMethod, SessionData
from providers.base import BaseProvider
from providers.common import best_thumbnail, build_download_base_options, build_extract_options
from utils.files import sanitize_filename
from utils.formatters import ellipsize, escape_html, format_date, format_duration, format_views


_YT_PATTERN = re.compile(
    r"(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be)(/.*)?",
    re.IGNORECASE,
)
_MIX_PREFIXES = ("RD", "RDMIX", "RDCL", "RDQ", "OLAK", "LL", "WL", "FL")
logger = logging.getLogger(__name__)


def get_playlist_id(url: str) -> str:
    try:
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return query.get("list", [""])[0]
    except Exception:
        return ""


def is_mix_playlist(list_id: str) -> bool:
    return bool(list_id and any(list_id.startswith(prefix) for prefix in _MIX_PREFIXES))


def is_regular_playlist(url: str) -> bool:
    list_id = get_playlist_id(url)
    if not list_id or is_mix_playlist(list_id):
        return False
    return list_id.startswith(("PL", "UU", "TL", "OL"))


class YouTubeProvider(BaseProvider):
    LOGIN_CHECK_URL = "https://www.youtube.com/feed/history"

    @property
    def key(self) -> str:
        return Platform.YOUTUBE.value

    def supports(self, url: str) -> bool:
        return bool(_YT_PATTERN.search(url))

    async def extract_info(self, url: str, *, user_id: int) -> MediaInfo:
        cookie_path, cookie_scope = self._resolve_cookie_path(user_id)
        self._log_cookie_resolution(
            user_id=user_id,
            action="extract_info",
            cookie_path=cookie_path,
            cookie_scope=cookie_scope,
        )
        list_id = get_playlist_id(url)
        mix = is_mix_playlist(list_id)

        if list_id and mix and cookie_path:
            try:
                playlist = await asyncio.to_thread(
                    _extract_playlist_info_sync,
                    url,
                    cookie_path,
                    self.settings.max_playlist_videos,
                    self.settings.ytdlp_ignore_config,
                    self._youtube_extractor_args(),
                )
                if playlist:
                    return playlist
            except yt_dlp.utils.DownloadError:
                pass

        if is_regular_playlist(url):
            try:
                playlist = await asyncio.to_thread(
                    _extract_playlist_info_sync,
                    url,
                    cookie_path,
                    self.settings.max_playlist_videos,
                    self.settings.ytdlp_ignore_config,
                    self._youtube_extractor_args(),
                )
                if playlist:
                    return playlist
            except yt_dlp.utils.DownloadError:
                pass

        try:
            info = await asyncio.to_thread(
                _extract_video_info_sync,
                url,
                cookie_path,
                self.settings.ytdlp_ignore_config,
                self._youtube_extractor_args(),
            )
        except yt_dlp.utils.DownloadError as exc:
            raise _map_ytdlp_error(exc) from exc
        if not info:
            raise BotError(
                ErrorCode.EXTRACTOR_FAILED,
                "Không thể lấy thông tin video YouTube.",
            )
        if info.get("is_live"):
            raise BotError(
                ErrorCode.EXTRACTOR_FAILED,
                "Bot chưa hỗ trợ livestream YouTube đang diễn ra.",
            )
        return MediaInfo(
            provider=Platform.YOUTUBE,
            source_url=info.get("webpage_url", url),
            title=info.get("title") or "Video YouTube",
            uploader=info.get("uploader") or info.get("channel") or "Không rõ",
            duration=info.get("duration"),
            thumbnail=best_thumbnail(info),
            view_count=info.get("view_count"),
            upload_date=info.get("upload_date"),
            is_live=bool(info.get("is_live")),
            is_mix=mix,
            media_kind=MediaKind.VIDEO,
            available_actions=["ytv", "yta", "ytdoc"],
        )

    async def check_login(self, user_id: int, url: str | None = None) -> tuple[bool, str]:
        cookie_path, cookie_scope = self._resolve_cookie_path(user_id)
        self._log_cookie_resolution(
            user_id=user_id,
            action="login_check",
            cookie_path=cookie_path,
            cookie_scope=cookie_scope,
        )
        if cookie_path is None:
            return False, "Chưa có cookie YouTube cho tài khoản này."
        target_url = url or self.LOGIN_CHECK_URL
        try:
            if url:
                info = await asyncio.to_thread(
                    _extract_video_info_sync,
                    target_url,
                    cookie_path,
                    self.settings.ytdlp_ignore_config,
                    self._youtube_extractor_args(),
                )
            else:
                info = await asyncio.to_thread(
                    _check_login_sync,
                    target_url,
                    cookie_path,
                    self.settings.ytdlp_ignore_config,
                    self._youtube_extractor_args(),
                )
        except yt_dlp.utils.DownloadError as exc:
            error = _map_ytdlp_error(exc)
            return False, error.user_message
        if not info:
            if url:
                return False, "Không thể xác minh quyền truy cập video này bằng cookie hiện tại."
            return False, "Không thể xác minh trạng thái đăng nhập YouTube bằng cookie hiện tại."
        if url:
            return True, f"Cookie hiện tại extract được video này: {info.get('title') or 'OK'}"
        return True, f"Cookie hợp lệ. YouTube đã phản hồi trang đăng nhập cá nhân: {info.get('title') or 'OK'}"

    def build_download_options(
        self,
        *,
        action: str,
        session: SessionData,
        output_dir: Path,
        item_index: int | None = None,
    ) -> DownloadPlan:
        output_dir.mkdir(parents=True, exist_ok=True)
        cookie_path, cookie_scope = self._resolve_cookie_path(session.user_id)
        self._log_cookie_resolution(
            user_id=session.user_id,
            action=action,
            cookie_path=cookie_path,
            cookie_scope=cookie_scope,
        )
        media_info = session.media_info
        title = media_info.title
        duration = media_info.duration
        source_url = session.source_url
        if action in {"ytplv", "ytpla", "ytpldoc"}:
            if item_index is None:
                raise ValueError("Playlist action requires item_index")
            entry = media_info.entries[item_index]
            title = entry.title
            duration = entry.duration
            source_url = entry.url

        options = build_download_base_options(
            output_dir=output_dir,
            cookiefile=cookie_path,
            ignore_config=self.settings.ytdlp_ignore_config,
            extractor_args=self._youtube_extractor_args(),
        )
        filename_base = sanitize_filename(title)
        caption_prefix = "📁" if action in {"ytdoc", "ytpldoc"} else ("🎵" if action in {"yta", "ytpla"} else "📺")
        caption = (
            f"{caption_prefix} <b>{escape_html(ellipsize(title, 80))}</b>\n"
            f"👤 {escape_html(media_info.uploader or 'Không rõ')}\n"
            f"⏱️ {escape_html(format_duration(duration))}"
        )

        if action in {"ytv", "ytplv", "ytdoc", "ytpldoc"}:
            options.update(
                {
                    "format": (
                        "bestvideo*[height<=1080]+bestaudio/best*[height<=1080]"
                        "/bestvideo*+bestaudio"
                        "/best"
                    ),
                    "merge_output_format": "mp4",
                }
            )
            return DownloadPlan(
                action=action,
                provider=Platform.YOUTUBE,
                backend=DownloadBackend.YT_DLP,
                send_method=SendMethod.DOCUMENT if action in {"ytdoc", "ytpldoc"} else SendMethod.VIDEO,
                source_url=source_url,
                output_template=options["outtmpl"],
                ydl_options=options,
                cobalt_request=self._build_cobalt_request(action=action, source_url=source_url),
                allowed_extensions=(".mp4", ".mkv", ".webm"),
                caption=caption,
                filename_hint=f"{filename_base}.mp4" if action in {"ytdoc", "ytpldoc"} else None,
                duration=duration,
                supports_streaming=action in {"ytv", "ytplv"},
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
            provider=Platform.YOUTUBE,
            backend=DownloadBackend.YT_DLP,
            send_method=SendMethod.AUDIO,
            source_url=source_url,
            output_template=options["outtmpl"],
            ydl_options=options,
            cobalt_request=self._build_cobalt_request(action=action, source_url=source_url),
            allowed_extensions=(".mp3", ".m4a", ".webm"),
            caption=caption.replace("📺", "🎵"),
            performer=media_info.uploader,
            track_title=ellipsize(title, 64),
            duration=duration,
        )

    def _resolve_cookie_path(self, user_id: int) -> tuple[Path | None, str]:
        user_cookie = self.cookie_store.cookie_path(user_id)
        if user_cookie.is_file():
            return user_cookie, "user"
        global_cookie = self.settings.youtube_global_cookie_file
        if global_cookie and global_cookie.is_file():
            return global_cookie, "global"
        return None, "none"

    def _log_cookie_resolution(
        self,
        *,
        user_id: int,
        action: str,
        cookie_path: Path | None,
        cookie_scope: str,
    ) -> None:
        cookie_size = "-"
        if cookie_path and cookie_path.exists():
            try:
                cookie_size = str(cookie_path.stat().st_size)
            except OSError:
                cookie_size = "?"
        logger.info(
            "Resolved YouTube cookie path scope=%s path=%s size=%s ignore_config=%s player_clients=%s skip=%s",
            cookie_scope,
            str(cookie_path) if cookie_path else "-",
            cookie_size,
            False,
            ",".join(self.settings.youtube_player_clients),
            ",".join(self.settings.youtube_skip),
            extra=log_extra(
                user_id=user_id,
                provider=self.key,
                action=action,
                status="cookie_resolved",
            ),
        )

    def _youtube_extractor_args(self) -> dict[str, Any]:
        args: dict[str, Any] = {}
        if self.settings.youtube_player_clients:
            args["youtube"] = {
                "player_client": list(self.settings.youtube_player_clients),
            }
            if self.settings.youtube_skip:
                args["youtube"]["skip"] = list(self.settings.youtube_skip)
        return args

    def _build_cobalt_request(self, *, action: str, source_url: str) -> dict[str, Any]:
        request: dict[str, Any] = {
            "url": source_url,
            "filenameStyle": "basic",
            "videoQuality": "1080",
            "youtubeVideoCodec": "h264",
            "youtubeVideoContainer": "mp4",
        }
        if action in {"yta", "ytpla"}:
            request.update(
                {
                    "downloadMode": "audio",
                    "audioFormat": "mp3",
                    "audioBitrate": "320",
                    "youtubeBetterAudio": True,
                }
            )
        return request


def _extract_video_info_sync(
    url: str,
    cookie_path: Path | None,
    ignore_config: bool,
    extractor_args: dict[str, Any],
) -> dict[str, Any]:
    options = build_extract_options(
        cookiefile=cookie_path,
        ignore_config=ignore_config,
        extractor_args=extractor_args,
    )
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError as exc:
        if "requested format is not available" not in str(exc).lower():
            raise
        fallback_options = build_extract_options(
            cookiefile=cookie_path,
            ignore_config=ignore_config,
            extractor_args=extractor_args,
        )
        fallback_options.update(
            {
                "format": "18/best",
                "extractor_args": {
                    "youtube": {
                        "player_client": list(
                            extractor_args.get("youtube", {}).get("player_client", ["android", "web"])
                        ),
                    }
                },
            }
        )
        with yt_dlp.YoutubeDL(fallback_options) as ydl:
            return ydl.extract_info(url, download=False)


def _extract_playlist_info_sync(
    url: str,
    cookie_path: Path | None,
    max_videos: int,
    ignore_config: bool,
    extractor_args: dict[str, Any],
) -> MediaInfo | None:
    options = build_extract_options(
        cookiefile=cookie_path,
        extract_flat=True,
        playlist_end=max_videos,
        ignore_config=ignore_config,
        extractor_args=extractor_args,
    )
    with yt_dlp.YoutubeDL(options) as ydl:
        info = ydl.extract_info(url, download=False)
    if not info:
        return None
    entries_raw = info.get("entries") or []
    entries = []
    for entry in entries_raw:
        if not entry or not entry.get("id"):
            continue
        entries.append(
            PlaylistEntry(
                id=str(entry["id"]),
                title=entry.get("title") or "Video không có tên",
                url=entry.get("url")
                or entry.get("webpage_url")
                or f"https://www.youtube.com/watch?v={entry['id']}",
                duration=entry.get("duration"),
            )
        )
    if not entries:
        return None
    available_actions = ["ytplv", "ytpla", "ytpldoc"]
    return MediaInfo(
        provider=Platform.YOUTUBE,
        source_url=info.get("webpage_url", url),
        title=info.get("title") or "Playlist YouTube",
        uploader=info.get("uploader") or info.get("channel") or "Không rõ",
        thumbnail=best_thumbnail(info),
        is_playlist=True,
        is_mix=is_mix_playlist(get_playlist_id(url)),
        media_kind=MediaKind.PLAYLIST,
        total_count=int(info.get("playlist_count") or len(entries_raw)),
        available_actions=available_actions,
        entries=entries,
        extra={"fetched_count": len(entries)},
    )


def _check_login_sync(
    url: str,
    cookie_path: Path | None,
    ignore_config: bool,
    extractor_args: dict[str, Any],
) -> dict[str, Any] | None:
    options = build_extract_options(
        cookiefile=cookie_path,
        extract_flat=True,
        playlist_end=1,
        ignore_config=ignore_config,
        extractor_args=extractor_args,
    )
    with yt_dlp.YoutubeDL(options) as ydl:
        return ydl.extract_info(url, download=False)


def _map_ytdlp_error(exc: Exception) -> BotError:
    message = str(exc).lower()
    if any(keyword in message for keyword in ("private", "unavailable", "404", "403")):
        return BotError(
            ErrorCode.PRIVATE_RESTRICTED,
            "Video đang riêng tư, bị gỡ hoặc không còn truy cập được.",
        )
    if any(
        keyword in message
        for keyword in (
            "login",
            "age",
            "sign in",
            "cookie",
            "confirm you're not a bot",
            "confirm you are not a bot",
            "not a bot",
        )
    ):
        return BotError(
            ErrorCode.AGE_LOGIN_REQUIRED,
            "Video này yêu cầu đăng nhập/xác minh từ YouTube. Hãy gửi cookies.txt của tài khoản YouTube rồi thử lại.",
        )
    return BotError(
        ErrorCode.EXTRACTOR_FAILED,
        "Không thể phân tích liên kết YouTube này.",
    )
