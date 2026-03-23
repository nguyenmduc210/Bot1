from __future__ import annotations

import asyncio
from pathlib import Path

from imageio_ffmpeg import get_ffmpeg_exe
from telegram import Bot, InputMediaPhoto
from telegram.constants import ParseMode

from models import BotError, DownloadedItem, ErrorCode, SendMethod
from utils.files import split_media_file
from utils.formatters import build_part_caption, format_size


class MediaSender:
    def __init__(self, *, telegram_file_limit_bytes: int, upload_read_timeout_seconds: int) -> None:
        self.telegram_file_limit_bytes = telegram_file_limit_bytes
        self.upload_read_timeout_seconds = upload_read_timeout_seconds
        self._ffmpeg_path = get_ffmpeg_exe()

    async def send_downloaded(
        self,
        *,
        bot: Bot,
        chat_id: int,
        item: DownloadedItem,
        progress_callback=None,
    ) -> int:
        if item.send_method == SendMethod.MEDIA_GROUP:
            await self.send_media_group(
                bot=bot,
                chat_id=chat_id,
                image_urls=item.image_urls,
                caption=item.caption,
                progress_callback=progress_callback,
            )
            return 0
        if item.file_path is None:
            raise BotError(ErrorCode.UPLOAD_FAILED, "Không có file để gửi lên Telegram.")
        if item.send_method == SendMethod.VIDEO:
            return await self.send_video(
                bot=bot,
                chat_id=chat_id,
                file_path=item.file_path,
                caption=item.caption,
                duration=item.duration,
                supports_streaming=item.supports_streaming,
                progress_callback=progress_callback,
            )
        if item.send_method == SendMethod.AUDIO:
            return await self.send_audio(
                bot=bot,
                chat_id=chat_id,
                file_path=item.file_path,
                caption=item.caption,
                performer=item.performer,
                title=item.track_title,
                duration=item.duration,
                progress_callback=progress_callback,
            )
        if item.send_method == SendMethod.DOCUMENT:
            return await self.send_document(
                bot=bot,
                chat_id=chat_id,
                file_path=item.file_path,
                caption=item.caption,
                filename_hint=item.filename_hint,
                progress_callback=progress_callback,
            )
        raise BotError(ErrorCode.UPLOAD_FAILED, "Không xác định được cách gửi file.")

    async def send_video(
        self,
        *,
        bot: Bot,
        chat_id: int,
        file_path: Path,
        caption: str,
        duration: int | None,
        supports_streaming: bool,
        progress_callback=None,
    ) -> int:
        if file_path.stat().st_size <= self.telegram_file_limit_bytes:
            with file_path.open("rb") as handle:
                await bot.send_video(
                    chat_id=chat_id,
                    video=handle,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    duration=duration,
                    supports_streaming=supports_streaming,
                    read_timeout=self.upload_read_timeout_seconds,
                )
            return file_path.stat().st_size
        return await self._send_split_file(
            bot=bot,
            chat_id=chat_id,
            file_path=file_path,
            caption=caption,
            is_video=True,
            send_method=SendMethod.VIDEO,
            progress_callback=progress_callback,
        )

    async def send_audio(
        self,
        *,
        bot: Bot,
        chat_id: int,
        file_path: Path,
        caption: str,
        performer: str | None,
        title: str | None,
        duration: int | None,
        progress_callback=None,
    ) -> int:
        if file_path.stat().st_size <= self.telegram_file_limit_bytes:
            with file_path.open("rb") as handle:
                await bot.send_audio(
                    chat_id=chat_id,
                    audio=handle,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    performer=performer,
                    title=title,
                    duration=duration,
                    read_timeout=self.upload_read_timeout_seconds,
                )
            return file_path.stat().st_size
        return await self._send_split_file(
            bot=bot,
            chat_id=chat_id,
            file_path=file_path,
            caption=caption,
            is_video=False,
            send_method=SendMethod.AUDIO,
            progress_callback=progress_callback,
        )

    async def send_document(
        self,
        *,
        bot: Bot,
        chat_id: int,
        file_path: Path,
        caption: str,
        filename_hint: str | None,
        progress_callback=None,
    ) -> int:
        if file_path.stat().st_size <= self.telegram_file_limit_bytes:
            with file_path.open("rb") as handle:
                await bot.send_document(
                    chat_id=chat_id,
                    document=handle,
                    filename=filename_hint,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    read_timeout=self.upload_read_timeout_seconds,
                )
            return file_path.stat().st_size
        return await self._send_split_file(
            bot=bot,
            chat_id=chat_id,
            file_path=file_path,
            caption=caption,
            is_video=True,
            send_method=SendMethod.DOCUMENT,
            filename_hint=filename_hint,
            progress_callback=progress_callback,
        )

    async def send_media_group(
        self,
        *,
        bot: Bot,
        chat_id: int,
        image_urls: list[str],
        caption: str,
        progress_callback=None,
    ) -> None:
        chunk_size = 10
        total_groups = (len(image_urls) + chunk_size - 1) // chunk_size
        for group_index, start in enumerate(range(0, len(image_urls), chunk_size), start=1):
            if progress_callback is not None:
                await progress_callback(
                    f"📤 <b>Đang gửi nhóm ảnh {group_index}/{total_groups}...</b>\n"
                    f"🖼️ <code>{min(chunk_size, len(image_urls) - start)}</code> ảnh"
                )
            group = image_urls[start : start + chunk_size]
            media_group = []
            for index, image_url in enumerate(group):
                if start == 0 and index == 0:
                    media_group.append(
                        InputMediaPhoto(
                            media=image_url,
                            caption=caption,
                            parse_mode=ParseMode.HTML,
                        )
                    )
                else:
                    media_group.append(InputMediaPhoto(media=image_url))
            await bot.send_media_group(chat_id=chat_id, media=media_group, read_timeout=self.upload_read_timeout_seconds)

    async def _send_split_file(
        self,
        *,
        bot: Bot,
        chat_id: int,
        file_path: Path,
        caption: str,
        is_video: bool,
        send_method: SendMethod,
        filename_hint: str | None = None,
        progress_callback=None,
    ) -> int:
        split_dir = file_path.parent / "chunks"
        parts = await asyncio.to_thread(
            split_media_file,
            file_path,
            split_dir,
            max_size_bytes=self.telegram_file_limit_bytes,
            is_video=is_video,
            ffmpeg_path=self._ffmpeg_path,
        )
        total = len(parts)
        for index, part in enumerate(parts, start=1):
            if progress_callback is not None:
                await progress_callback(
                    f"📤 <b>Đang gửi phần {index}/{total}...</b>\n"
                    f"📦 <code>{format_size(part.stat().st_size)}</code>"
                )
            part_caption = build_part_caption(caption, index, total)
            if send_method == SendMethod.VIDEO:
                with part.open("rb") as handle:
                    await bot.send_video(
                        chat_id=chat_id,
                        video=handle,
                        caption=part_caption,
                        parse_mode=ParseMode.HTML,
                        supports_streaming=True,
                        read_timeout=self.upload_read_timeout_seconds,
                    )
            elif send_method == SendMethod.AUDIO:
                with part.open("rb") as handle:
                    await bot.send_audio(
                        chat_id=chat_id,
                        audio=handle,
                        caption=part_caption,
                        parse_mode=ParseMode.HTML,
                        read_timeout=self.upload_read_timeout_seconds,
                    )
            else:
                with part.open("rb") as handle:
                    await bot.send_document(
                        chat_id=chat_id,
                        document=handle,
                        filename=filename_hint,
                        caption=part_caption,
                        parse_mode=ParseMode.HTML,
                        read_timeout=self.upload_read_timeout_seconds,
                    )
        return file_path.stat().st_size
