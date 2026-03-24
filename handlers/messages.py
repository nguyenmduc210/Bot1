from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from handlers.common import get_services
from logging_setup import log_extra
from models import BotError, MediaInfo, MediaKind, Platform
from providers import detect_provider
from utils.formatters import ellipsize, escape_html, format_date, format_duration, format_views


logger = logging.getLogger(__name__)


def detect_platform(url: str, context: ContextTypes.DEFAULT_TYPE) -> str | None:
    provider = detect_provider(url, get_services(context).providers)
    return provider.key if provider else None


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user = update.effective_user
    message = update.effective_message
    document = message.document if message else None
    if not user or not message or not document:
        return

    filename = (document.file_name or "").lower()
    is_cookie_file = filename.endswith(".txt") and (
        "cookie" in filename or document.mime_type in ("text/plain", "application/octet-stream")
    )
    if not is_cookie_file:
        return

    if document.file_size and document.file_size > services.settings.cookie_max_size_bytes:
        await message.reply_text(
            "❌ <b>File cookie quá lớn</b>\n\nGiới hạn hiện tại là 2 MB.",
            parse_mode=ParseMode.HTML,
        )
        return

    status = await message.reply_text("⏳ <b>Đang xử lý file cookie...</b>", parse_mode=ParseMode.HTML)
    temp_path: Path | None = None
    try:
        telegram_file = await context.bot.get_file(document.file_id)
        with tempfile.NamedTemporaryFile(
            suffix=".txt",
            delete=False,
            dir=services.settings.temp_root,
        ) as handle:
            temp_path = Path(handle.name)
        await telegram_file.download_to_drive(str(temp_path))
        metadata = await services.cookie_store.save_cookie_file(user.id, temp_path)
        updated = metadata.updated_at.astimezone().strftime("%d/%m/%Y %H:%M")
        await status.edit_text(
            (
                "✅ <b>Cookie YouTube đã được lưu thành công!</b>\n\n"
                f"📊 <code>{metadata.line_count}</code> mục · Cập nhật: <code>{updated}</code>\n\n"
                "Từ bây giờ bot sẽ tự dùng cookie của bạn cho YouTube Mix/playlist cá nhân hóa.\n"
                "🍪 Xem trạng thái: /mycookie\n"
                "🗑️ Xóa cookie: /delcookie"
            ),
            parse_mode=ParseMode.HTML,
        )
    except ValueError as exc:
        await status.edit_text(
            f"❌ <b>File cookie không hợp lệ</b>\n\n{escape_html(str(exc))}",
            parse_mode=ParseMode.HTML,
        )
    except Exception as exc:
        logger.exception("Cookie upload failed", extra=log_extra(user_id=user.id, action="cookie_upload", status="error"))
        await services.telegram_log_service.send_exception(
            bot=context.bot,
            title="Cookie upload failed",
            error=exc,
            user_id=user.id,
            chat_id=message.chat_id,
            action="cookie_upload",
            extra_lines=[f"filename={filename or '-'}"],
        )
        await status.edit_text(
            "❌ <b>Không thể lưu file cookie lúc này.</b>\n\nHãy thử lại với file <code>cookies.txt</code> Netscape hợp lệ.",
            parse_mode=ParseMode.HTML,
        )
    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink(missing_ok=True)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user = update.effective_user
    message = update.effective_message
    if not user or not message or not message.text:
        return

    url = message.text.strip()
    await services.stats_store.record_request(user.id)
    await services.session_store.cleanup_expired()

    remaining = await services.rate_limiter.check_and_update(user.id)
    if remaining > 0:
        await message.reply_text(
            (
                f"⏳ <b>Vui lòng chờ {remaining:.0f} giây</b> trước khi gửi yêu cầu tiếp theo.\n\n"
                "Bot đang áp dụng giới hạn tần suất để đảm bảo ổn định khi nhiều user dùng cùng lúc."
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    provider = detect_provider(url, services.providers)
    if provider is None:
        await message.reply_text(
            (
                "❌ <b>Link không được nhận dạng</b>\n\n"
                "Bot hiện hỗ trợ:\n"
                "▸ <code>facebook.com</code> / <code>fb.com</code> / <code>fb.watch</code>\n"
                "▸ <code>tiktok.com</code> / <code>vt.tiktok.com</code>\n"
                "▸ <code>soundcloud.com</code> / <code>on.soundcloud.com</code>\n"
                "▸ <code>youtube.com</code> / <code>youtu.be</code>\n\n"
                "Vui lòng kiểm tra lại đường dẫn."
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    status = await message.reply_text(
        f"⏳ <b>Đang phân tích liên kết {provider.key.title()}...</b>",
        parse_mode=ParseMode.HTML,
    )
    try:
        media_info = await provider.extract_info(url, user_id=user.id)
        session = services.session_store.build_session(user_id=user.id, media_info=media_info, source_url=media_info.source_url)
        await services.session_store.create_session(session)
        keyboard = _build_keyboard(media_info, session.job_id)
        caption = _build_preview_caption(media_info)
        await status.delete()
        await _reply_preview(message, media_info.thumbnail, caption, keyboard)
        logger.info(
            "Prepared preview",
            extra=log_extra(user_id=user.id, provider=provider.key, job_id=session.job_id, status="ok"),
        )
    except BotError as exc:
        logger.warning(
            "Extractor failed",
            extra=log_extra(user_id=user.id, provider=provider.key, status=exc.code.value),
        )
        await services.telegram_log_service.send_bot_error(
            bot=context.bot,
            title="Extractor failed",
            error=exc,
            user_id=user.id,
            chat_id=message.chat_id,
            provider=provider.key,
            extra_lines=[f"url={url}"],
        )
        await status.edit_text(f"❌ <b>{escape_html(exc.user_message)}</b>", parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.exception(
            "Unexpected extract error",
            extra=log_extra(user_id=user.id, provider=provider.key, status="error"),
        )
        await services.telegram_log_service.send_exception(
            bot=context.bot,
            title="Unexpected extract error",
            error=exc,
            user_id=user.id,
            chat_id=message.chat_id,
            provider=provider.key,
            extra_lines=[f"url={url}"],
        )
        await status.edit_text(
            "❌ <b>Bot không thể xử lý liên kết này lúc này.</b>\n\nHãy thử lại sau ít phút.",
            parse_mode=ParseMode.HTML,
        )


def _build_keyboard(media_info: MediaInfo, job_id: str) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    count = len(media_info.entries)
    if media_info.provider == Platform.YOUTUBE:
        if media_info.media_kind == MediaKind.PLAYLIST:
            buttons.append(
                [
                    InlineKeyboardButton(f"📺 Tải {count} Video (1080p)", callback_data=f"ytplv:{job_id}"),
                    InlineKeyboardButton(f"🎵 Tải {count} MP3 (320kbps)", callback_data=f"ytpla:{job_id}"),
                ]
            )
            buttons.append(
                [InlineKeyboardButton(f"📁 Tải {count} MP4 File (1080p · File gốc)", callback_data=f"ytpldoc:{job_id}")]
            )
        else:
            buttons.append(
                [
                    InlineKeyboardButton("📺 Tải Video (1080p)", callback_data=f"ytv:{job_id}"),
                    InlineKeyboardButton("🎵 Tải MP3 (320kbps)", callback_data=f"yta:{job_id}"),
                ]
            )
            buttons.append(
                [InlineKeyboardButton("📁 Tải MP4 File (1080p · File gốc)", callback_data=f"ytdoc:{job_id}")]
            )
    elif media_info.provider == Platform.FACEBOOK:
        buttons.append(
            [
                InlineKeyboardButton("📹 Tải Video (1080p)", callback_data=f"fbv:{job_id}"),
                InlineKeyboardButton("🎵 Tải MP3 (320kbps)", callback_data=f"fba:{job_id}"),
            ]
        )
        buttons.append(
            [InlineKeyboardButton("📁 Tải MP4 File (1080p · File gốc)", callback_data=f"fbdoc:{job_id}")]
        )
    elif media_info.provider == Platform.TIKTOK:
        if media_info.media_kind == MediaKind.ALBUM:
            row = [
                InlineKeyboardButton(
                    f"📸 Tải Album Ảnh ({len(media_info.image_urls)} ảnh)",
                    callback_data=f"img:{job_id}",
                )
            ]
            if "mus" in media_info.available_actions:
                row.append(InlineKeyboardButton("🎵 Tải Nhạc", callback_data=f"mus:{job_id}"))
            buttons.append(row)
        else:
            row = [InlineKeyboardButton("🎬 Tải Video (No Watermark)", callback_data=f"vid:{job_id}")]
            if "mus" in media_info.available_actions:
                row.append(InlineKeyboardButton("🎵 Tải Nhạc", callback_data=f"mus:{job_id}"))
            buttons.append(row)
            buttons.append([InlineKeyboardButton("📁 Tải MP4 1080p (File gốc)", callback_data=f"tkdoc:{job_id}")])
    elif media_info.provider == Platform.SOUNDCLOUD:
        if media_info.media_kind == MediaKind.PLAYLIST:
            buttons.append(
                [InlineKeyboardButton(f"🎵 Tải {count} Track (Âm thanh gốc)", callback_data=f"scplmus:{job_id}")]
            )
        else:
            buttons.append([InlineKeyboardButton("🎵 Tải Âm Thanh Gốc", callback_data=f"scmus:{job_id}")])
    return InlineKeyboardMarkup(buttons)


def _build_preview_caption(media_info: MediaInfo) -> str:
    title = escape_html(ellipsize(media_info.title, 78))
    uploader = escape_html(media_info.uploader or "Không rõ")
    if media_info.provider == Platform.YOUTUBE:
        if media_info.media_kind == MediaKind.PLAYLIST:
            total = media_info.total_count or len(media_info.entries)
            fetched = len(media_info.entries)
            cap_note = ""
            if fetched < total:
                cap_note = f"\n⚠️ Bot đang lấy tối đa {fetched}/{total} video đầu."
            source_note = "\n🍪 Playlist cá nhân hóa từ cookie." if media_info.is_mix else ""
            return (
                f"📋 <b>{title}</b>\n\n"
                f"👤 Kênh: <code>{uploader}</code>\n"
                f"🎞️ Số video: <code>{fetched}</code>"
                + (f" / {total}" if total else "")
                + f"{source_note}{cap_note}\n\n"
                "👇 <b>Chọn định dạng tải xuống:</b>"
            )
        mix_note = "\n\n🎲 Đây là video thuộc YouTube Mix." if media_info.is_mix else ""
        return (
            f"📺 <b>{title}</b>\n\n"
            f"👤 Kênh: <code>{uploader}</code>\n"
            f"⏱️ Thời lượng: <code>{escape_html(format_duration(media_info.duration))}</code>\n"
            f"👁️ Lượt xem: <code>{escape_html(format_views(media_info.view_count))}</code>\n"
            f"📅 Ngày đăng: <code>{escape_html(format_date(media_info.upload_date))}</code>"
            f"{mix_note}\n\n"
            "👇 <b>Chọn định dạng tải xuống:</b>"
        )
    if media_info.provider == Platform.FACEBOOK:
        return (
            f"📹 <b>{title}</b>\n\n"
            f"👤 Tác giả: <code>{uploader}</code>\n"
            f"⏱️ Thời lượng: <code>{escape_html(format_duration(media_info.duration))}</code>\n"
            f"📅 Ngày đăng: <code>{escape_html(format_date(media_info.upload_date))}</code>\n\n"
            "👇 <b>Chọn định dạng tải xuống:</b>"
        )
    if media_info.provider == Platform.TIKTOK:
        if media_info.media_kind == MediaKind.ALBUM:
            return (
                f"📸 <b>{title}</b>\n\n"
                f"📋 Loại nội dung: <code>Album ảnh</code>\n"
                f"🖼️ Số ảnh: <code>{len(media_info.image_urls)}</code>\n"
                f"🌐 Nguồn dữ liệu: {escape_html(str(media_info.extra.get('source_name') or 'TikTok'))}\n\n"
                "👇 <b>Chọn định dạng tải xuống:</b>"
            )
        return (
            f"🎬 <b>{title}</b>\n\n"
            f"📋 Loại nội dung: <code>Video</code>\n"
            f"ℹ️ Chi tiết: <code>HD · Không watermark</code>\n"
            f"🌐 Nguồn dữ liệu: {escape_html(str(media_info.extra.get('source_name') or 'TikTok'))}\n\n"
            "👇 <b>Chọn định dạng tải xuống:</b>"
        )
    if media_info.provider == Platform.SOUNDCLOUD:
        if media_info.media_kind == MediaKind.PLAYLIST:
            total = media_info.total_count or len(media_info.entries)
            fetched = len(media_info.entries)
            return (
                f"🎧 <b>{title}</b>\n\n"
                f"👤 Nghệ sĩ: <code>{uploader}</code>\n"
                f"🎼 Số track: <code>{fetched}</code>"
                + (f" / {total}" if total else "")
                + "\n\n👇 <b>Chọn định dạng tải xuống:</b>"
            )
        return (
            f"🎧 <b>{title}</b>\n\n"
            f"👤 Nghệ sĩ: <code>{uploader}</code>\n"
            f"⏱️ Thời lượng: <code>{escape_html(format_duration(media_info.duration))}</code>\n"
            f"🎚️ Chất lượng: <code>Âm thanh gốc</code>\n\n"
            "👇 <b>Nhấn nút bên dưới để tải xuống:</b>"
        )
    return (
        f"🎧 <b>{title}</b>\n\n"
        f"👤 Nghệ sĩ: <code>{uploader}</code>\n"
        f"⏱️ Thời lượng: <code>{escape_html(format_duration(media_info.duration))}</code>\n"
        f"🎚️ Chất lượng: <code>MP3 320kbps</code>\n\n"
        "👇 <b>Nhấn nút bên dưới để tải xuống:</b>"
    )


async def _reply_preview(message, thumbnail: str | None, caption: str, keyboard: InlineKeyboardMarkup) -> None:
    if thumbnail:
        try:
            await message.reply_photo(
                photo=thumbnail,
                caption=caption,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
            return
        except Exception:
            pass
    await message.reply_text(
        caption,
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
    )
