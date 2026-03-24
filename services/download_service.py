from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import yt_dlp
from imageio_ffmpeg import get_ffmpeg_exe

from config import Settings
from logging_setup import log_extra
from models import BotError, DownloadBackend, DownloadedItem, ErrorCode, SendMethod, SessionData
from providers.base import BaseProvider
from services.http_client import AsyncHTTPClient
from utils.files import extract_audio_from_video, sanitize_filename, validate_output_file


logger = logging.getLogger(__name__)


class DownloadService:
    def __init__(self, http_client: AsyncHTTPClient, settings: Settings, *, max_concurrent_downloads: int) -> None:
        self.http_client = http_client
        self.settings = settings
        self._semaphore = asyncio.Semaphore(max_concurrent_downloads)
        self._ffmpeg_path = get_ffmpeg_exe()

    async def run(
        self,
        *,
        provider: BaseProvider,
        session: SessionData,
        action: str,
        output_dir: Path,
        item_index: int | None = None,
    ) -> DownloadedItem:
        plan = provider.build_download_options(
            action=action,
            session=session,
            output_dir=output_dir,
            item_index=item_index,
        )
        async with self._semaphore:
            return await self._execute_plan(plan, session=session)

    async def _execute_plan(self, plan, *, session: SessionData) -> DownloadedItem:
        if plan.backend == DownloadBackend.MEDIA_GROUP:
            return DownloadedItem(
                send_method=plan.send_method,
                caption=plan.caption,
                image_urls=plan.image_urls,
            )

        if plan.backend == DownloadBackend.DIRECT:
            if plan.output_path is None or plan.source_url is None:
                raise BotError(ErrorCode.DOWNLOAD_FAILED, "Không thể khởi tạo tải file trực tiếp.")
            file_path = await self._download_direct(plan, session=session)
        elif plan.backend == DownloadBackend.YT_DLP:
            file_path = await self._download_with_ytdlp(plan)
        else:
            raise BotError(ErrorCode.DOWNLOAD_FAILED, "Backend tải xuống không hợp lệ.")

        if plan.converted_output_path is not None:
            try:
                file_path = await asyncio.to_thread(
                    extract_audio_from_video,
                    input_file=file_path,
                    output_file=plan.converted_output_path,
                    ffmpeg_path=self._ffmpeg_path,
                )
            except RuntimeError as exc:
                raise BotError(
                    ErrorCode.CONVERSION_FAILED,
                    "Không thể tách âm thanh từ video TikTok này.",
                    internal_message=str(exc),
                ) from exc

        try:
            validate_output_file(file_path, plan.allowed_extensions)
        except (FileNotFoundError, ValueError) as exc:
            raise BotError(
                ErrorCode.DOWNLOAD_FAILED,
                "File tải xuống không hợp lệ hoặc bị lỗi.",
                internal_message=str(exc),
            ) from exc

        return DownloadedItem(
            send_method=plan.send_method,
            caption=plan.caption,
            file_path=file_path,
            file_size=file_path.stat().st_size,
            filename_hint=plan.filename_hint,
            performer=plan.performer,
            track_title=plan.track_title,
            duration=plan.duration,
            supports_streaming=plan.supports_streaming,
        )

    async def _download_direct(self, plan, *, session: SessionData) -> Path:
        assert plan.output_path is not None
        candidates = [plan.source_url, *plan.fallback_urls]
        last_error: Exception | None = None
        for candidate in [url for url in candidates if url]:
            try:
                await self.http_client.download_file(candidate, plan.output_path, headers=plan.headers)
                return plan.output_path
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Direct download failed, trying fallback",
                    extra=log_extra(
                        user_id=session.user_id,
                        provider=session.provider.value,
                        action=plan.action,
                        job_id=session.job_id,
                        status="retry",
                    ),
                )
        raise BotError(ErrorCode.DOWNLOAD_FAILED, "Không thể tải file từ máy chủ nguồn.") from last_error

    async def _download_with_ytdlp(self, plan) -> Path:
        cookiefile = plan.ydl_options.get("cookiefile") if getattr(plan, "ydl_options", None) else None
        logger.info(
            "Starting yt-dlp download cookiefile=%s source=%s",
            cookiefile or "-",
            plan.source_url or "-",
            extra=log_extra(
                provider=plan.provider.value if getattr(plan, "provider", None) else "-",
                action=plan.action,
                status="yt_dlp_start",
            ),
        )
        try:
            await asyncio.to_thread(_run_ytdlp_sync, plan.ydl_options, plan.source_url)
        except yt_dlp.utils.DownloadError as exc:
            message = str(exc).lower()
            logger.warning(
                "yt-dlp download failed source=%s detail=%s",
                plan.source_url or "-",
                str(exc),
                extra=log_extra(
                    provider=plan.provider.value if getattr(plan, "provider", None) else "-",
                    action=plan.action,
                    status="yt_dlp_failed",
                ),
            )
            if "requested format is not available" in message:
                retry_options = _build_requested_format_retry_options(plan)
                if retry_options is not None:
                    retry_cookiefile = retry_options.get("cookiefile")
                    logger.info(
                        "Retrying yt-dlp with relaxed format cookiefile=%s source=%s",
                        retry_cookiefile or "-",
                        plan.source_url or "-",
                        extra=log_extra(
                            provider=plan.provider.value if getattr(plan, "provider", None) else "-",
                            action=plan.action,
                            status="yt_dlp_retry_format",
                        ),
                    )
                    try:
                        await asyncio.to_thread(_run_ytdlp_sync, retry_options, plan.source_url)
                        output_dir = Path(plan.output_template).parent if plan.output_template else Path(".")
                        return _pick_downloaded_file(output_dir)
                    except yt_dlp.utils.DownloadError as retry_exc:
                        logger.warning(
                            "yt-dlp retry failed source=%s detail=%s",
                            plan.source_url or "-",
                            str(retry_exc),
                            extra=log_extra(
                                provider=plan.provider.value if getattr(plan, "provider", None) else "-",
                                action=plan.action,
                                status="yt_dlp_retry_failed",
                            ),
                        )
                        message = str(retry_exc).lower()
                        exc = retry_exc
            if any(
                keyword in message
                for keyword in (
                    "login",
                    "cookie",
                    "age",
                    "sign in",
                    "confirm you're not a bot",
                    "confirm you are not a bot",
                    "not a bot",
                )
            ):
                raise BotError(
                    ErrorCode.AGE_LOGIN_REQUIRED,
                    "Nội dung này yêu cầu đăng nhập/xác minh từ YouTube. Hãy thêm cookies.txt rồi thử lại.",
                ) from exc
            if any(keyword in message for keyword in ("private", "unavailable", "403", "404")):
                raise BotError(
                    ErrorCode.PRIVATE_RESTRICTED,
                    "Nội dung đang riêng tư hoặc bị giới hạn truy cập.",
                ) from exc
            if self._can_use_cobalt(plan):
                logger.info(
                    "yt-dlp failed, trying Cobalt API source=%s",
                    plan.source_url or "-",
                    extra=log_extra(
                        provider=plan.provider.value if getattr(plan, "provider", None) else "-",
                        action=plan.action,
                        status="cobalt_fallback_start",
                    ),
                )
                try:
                    return await self._download_with_cobalt(plan)
                except BotError as fallback_exc:
                    logger.warning(
                        "Cobalt fallback failed source=%s detail=%s",
                        plan.source_url or "-",
                        fallback_exc.internal_message,
                        extra=log_extra(
                            provider=plan.provider.value if getattr(plan, "provider", None) else "-",
                            action=plan.action,
                            status="cobalt_fallback_failed",
                        ),
                    )
                    raise BotError(
                        ErrorCode.DOWNLOAD_FAILED,
                        "yt-dlp lỗi và Cobalt API cũng không thể tải nội dung này.",
                    ) from fallback_exc
            raise BotError(ErrorCode.DOWNLOAD_FAILED, "yt-dlp không thể tải nội dung này.") from exc
        except Exception as exc:
            raise BotError(ErrorCode.DOWNLOAD_FAILED, "Tải xuống thất bại do lỗi hệ thống.") from exc

        output_dir = Path(plan.output_template).parent if plan.output_template else Path(".")
        return _pick_downloaded_file(output_dir)

    async def _download_with_cobalt(self, plan) -> Path:
        cobalt_url = (self.settings.cobalt_api_url or "").rstrip("/")
        if not cobalt_url or not getattr(plan, "cobalt_request", None):
            raise BotError(ErrorCode.DOWNLOAD_FAILED, "Cobalt API chưa được cấu hình cho tác vụ này.")

        try:
            payload = await self.http_client.post_json(
                cobalt_url,
                json_body=plan.cobalt_request,
                headers=_build_cobalt_headers(self.settings),
                timeout_seconds=max(self.settings.http_timeout_seconds, 45.0),
            )
        except Exception as exc:
            raise BotError(
                ErrorCode.DOWNLOAD_FAILED,
                "Không thể kết nối Cobalt API lúc này.",
                internal_message=f"Cobalt API request failed: {exc}",
            ) from exc

        status = str(payload.get("status") or "").lower()
        if status in {"redirect", "tunnel"}:
            download_url = payload.get("url")
            if not isinstance(download_url, str) or not download_url:
                raise BotError(ErrorCode.DOWNLOAD_FAILED, "Cobalt API trả về URL tải không hợp lệ.")
            output_dir = Path(plan.output_template).parent if plan.output_template else Path(".")
            filename = _resolve_cobalt_filename(payload.get("filename"), plan)
            destination = output_dir / filename
            try:
                await self.http_client.download_file(download_url, destination)
            except Exception as exc:
                raise BotError(
                    ErrorCode.DOWNLOAD_FAILED,
                    "Cobalt API trả link nhưng bot không tải được file.",
                    internal_message=f"Cobalt file download failed: {exc}",
                ) from exc
            return destination

        if status == "error":
            error = payload.get("error") or {}
            code = error.get("code") if isinstance(error, dict) else None
            message = "Cobalt API từ chối xử lý nội dung này."
            if isinstance(code, str) and code.startswith("api.auth."):
                message = "Cobalt API yêu cầu xác thực. Hãy cấu hình API key hoặc bearer token."
            raise BotError(
                ErrorCode.DOWNLOAD_FAILED,
                message,
                internal_message=f"Cobalt API error: {code or 'unknown'}",
            )

        if status == "local-processing":
            raise BotError(
                ErrorCode.DOWNLOAD_FAILED,
                "Cobalt API yêu cầu local processing, bot chưa hỗ trợ nhánh này.",
            )

        if status == "picker":
            raise BotError(
                ErrorCode.DOWNLOAD_FAILED,
                "Cobalt API trả về nhiều media và không thể tự chọn an toàn.",
            )

        raise BotError(
            ErrorCode.DOWNLOAD_FAILED,
            "Cobalt API trả về phản hồi không hợp lệ.",
            internal_message=f"Unexpected Cobalt status: {status or 'missing'}",
        )

    def _can_use_cobalt(self, plan) -> bool:
        return bool(self.settings.cobalt_api_url and getattr(plan, "cobalt_request", None))


def _run_ytdlp_sync(ydl_options: dict, url: str | None) -> None:
    if not url:
        raise ValueError("Missing source URL for yt-dlp")
    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        ydl.download([url])


def _pick_downloaded_file(output_dir: Path) -> Path:
    candidates = [
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.suffix not in {".part", ".ytdl"}
    ]
    if not candidates:
        raise BotError(ErrorCode.DOWNLOAD_FAILED, "Không tìm thấy file sau khi tải xong.")
    candidates.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0]


def _build_requested_format_retry_options(plan):
    if not getattr(plan, "ydl_options", None):
        return None
    retry_options = dict(plan.ydl_options)
    retry_options["ignoreconfig"] = True
    if getattr(plan, "provider", None) and plan.provider.value == "youtube":
        retry_options["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "web"],
            }
        }
    if getattr(plan, "send_method", None) in {SendMethod.VIDEO, SendMethod.DOCUMENT}:
        retry_options["format"] = "bestvideo*+bestaudio/best*"
    elif getattr(plan, "send_method", None) == SendMethod.AUDIO:
        if getattr(plan, "provider", None) and plan.provider.value == "tiktok":
            retry_options["format"] = "best"
        else:
            retry_options["format"] = "bestaudio/best"
    return retry_options


def _build_cobalt_headers(settings: Settings) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if settings.cobalt_api_key:
        headers["Authorization"] = f"Api-Key {settings.cobalt_api_key}"
    elif settings.cobalt_bearer_token:
        headers["Authorization"] = f"Bearer {settings.cobalt_bearer_token}"
    return headers


def _resolve_cobalt_filename(filename: Any, plan) -> str:
    raw_name = Path(str(filename or plan.filename_hint or "media")).name
    stem = sanitize_filename(Path(raw_name).stem or "media")
    suffix = Path(raw_name).suffix.lower()
    if not suffix:
        suffix = _default_extension_for_plan(plan)
    return f"{stem}{suffix}"


def _default_extension_for_plan(plan) -> str:
    if getattr(plan, "filename_hint", None):
        hint_suffix = Path(plan.filename_hint).suffix.lower()
        if hint_suffix:
            return hint_suffix
    if getattr(plan, "allowed_extensions", None):
        return plan.allowed_extensions[0]
    if getattr(plan, "send_method", None) in {SendMethod.VIDEO, SendMethod.DOCUMENT}:
        return ".mp4"
    return ".mp3"
