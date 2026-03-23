from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from handlers.common import get_services
from logging_setup import log_extra
from models import BotError, ErrorCode, SendMethod, SessionData
from utils.files import remove_tree
from utils.formatters import escape_html


logger = logging.getLogger(__name__)

PLAYLIST_ACTIONS = {"ytplv", "ytpla", "ytpldoc"}
ALBUM_ACTIONS = {"img"}


@dataclass(slots=True)
class CallbackRoute:
    action: str
    is_playlist: bool
    is_album: bool


def parse_callback_data(data: str) -> tuple[str, str]:
    action, job_id = data.split(":", 1)
    return action, job_id


def resolve_callback_route(action: str) -> CallbackRoute:
    return CallbackRoute(
        action=action,
        is_playlist=action in PLAYLIST_ACTIONS,
        is_album=action in ALBUM_ACTIONS,
    )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    query = update.callback_query
    if query is None or query.from_user is None or query.message is None:
        return
    await query.answer()

    try:
        action, job_id = parse_callback_data(query.data)
    except ValueError:
        await query.message.reply_text("⚠️ Callback không hợp lệ.", parse_mode=ParseMode.HTML)
        return

    session = await services.session_store.get_session(job_id, user_id=query.from_user.id)
    if session is None:
        await _send_session_expired(query.message)
        return

    route = resolve_callback_route(action)
    provider = services.providers[session.provider.value]
    status = await query.message.reply_text(
        "🔄 <b>Đang khởi tạo tiến trình tải...</b>",
        parse_mode=ParseMode.HTML,
    )

    try:
        if route.is_playlist:
            await _handle_playlist_action(
                session=session,
                action=action,
                query_message=query.message,
                status_message=status,
                context=context,
            )
        else:
            await _handle_single_or_album_action(
                session=session,
                action=action,
                query_message=query.message,
                status_message=status,
                context=context,
            )
        logger.info(
            "Callback handled",
            extra=log_extra(
                user_id=query.from_user.id,
                provider=provider.key,
                action=action,
                job_id=job_id,
                status="ok",
            ),
        )
    except BotError as exc:
        if not route.is_playlist:
            await services.stats_store.record_item_processed(
                user_id=session.user_id,
                success=False,
                item_count=1,
            )
        logger.warning(
            "Callback failed detail=%s",
            exc.internal_message,
            extra=log_extra(
                user_id=query.from_user.id,
                provider=provider.key,
                action=action,
                job_id=job_id,
                status=exc.code.value,
            ),
        )
        await services.telegram_log_service.send_bot_error(
            bot=context.bot,
            title="Callback failed",
            error=exc,
            user_id=query.from_user.id,
            chat_id=query.message.chat_id,
            provider=provider.key,
            action=action,
            job_id=job_id,
        )
        await _safe_edit(status, f"❌ <b>{exc.user_message}</b>")
    except Exception as exc:
        if not route.is_playlist:
            await services.stats_store.record_item_processed(
                user_id=session.user_id,
                success=False,
                item_count=1,
            )
        logger.exception(
            "Unexpected callback error",
            extra=log_extra(
                user_id=query.from_user.id,
                provider=provider.key,
                action=action,
                job_id=job_id,
                status="error",
            ),
        )
        await services.telegram_log_service.send_exception(
            bot=context.bot,
            title="Unexpected callback error",
            error=exc,
            user_id=query.from_user.id,
            chat_id=query.message.chat_id,
            provider=provider.key,
            action=action,
            job_id=job_id,
        )
        await _safe_edit(
            status,
            "❌ <b>Bot gặp lỗi hệ thống khi xử lý yêu cầu này.</b>\n\nHãy thử lại sau ít phút.",
        )


async def _handle_single_or_album_action(
    *,
    session: SessionData,
    action: str,
    query_message: Message,
    status_message: Message,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    services = get_services(context)
    provider = services.providers[session.provider.value]
    temp_path = Path(tempfile.mkdtemp(prefix=f"{session.job_id}_", dir=services.settings.temp_root))
    try:
        item = await services.download_service.run(
            provider=provider,
            session=session,
            action=action,
            output_dir=temp_path,
        )
        if item.send_method == SendMethod.MEDIA_GROUP:
            await _safe_edit(status_message, "📸 <b>Đang gửi album ảnh...</b>")
        else:
            await _safe_edit(status_message, "📤 <b>Đang gửi file lên Telegram...</b>")
        bytes_sent = await services.media_sender.send_downloaded(
            bot=context.bot,
            chat_id=query_message.chat_id,
            item=item,
            progress_callback=lambda text: _safe_edit(status_message, text),
        )
        await services.stats_store.record_item_processed(
            user_id=session.user_id,
            success=True,
            bytes_sent=bytes_sent,
            item_count=1,
        )
        try:
            await status_message.delete()
        except Exception:
            pass
    finally:
        remove_tree(temp_path)


async def _handle_playlist_action(
    *,
    session: SessionData,
    action: str,
    query_message: Message,
    status_message: Message,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    services = get_services(context)
    provider = services.providers[session.provider.value]
    if not session.media_info.entries:
        raise BotError(ErrorCode.DOWNLOAD_FAILED, "Playlist trống hoặc không có video hợp lệ.")

    success_count = 0
    failure_count = 0
    entries = session.media_info.entries
    base_dir = Path(tempfile.mkdtemp(prefix=f"{session.job_id}_", dir=services.settings.temp_root))
    try:
        for index, entry in enumerate(entries, start=1):
            progress = _playlist_progress_text(
                title=session.media_info.title,
                current_title=entry.title,
                index=index,
                total=len(entries),
                success_count=success_count,
                failure_count=failure_count,
            )
            await _safe_edit(status_message, progress)
            try:
                item = await services.download_service.run(
                    provider=provider,
                    session=session,
                    action=action,
                    output_dir=base_dir / f"item_{index:03d}",
                    item_index=index - 1,
                )
                await services.media_sender.send_downloaded(
                    bot=context.bot,
                    chat_id=query_message.chat_id,
                    item=item,
                    progress_callback=lambda text: _safe_edit(status_message, text),
                )
                await services.stats_store.record_item_processed(
                    user_id=session.user_id,
                    success=True,
                    bytes_sent=item.file_size,
                    item_count=1,
                )
                success_count += 1
            except BotError as exc:
                failure_count += 1
                await services.stats_store.record_item_processed(
                    user_id=session.user_id,
                    success=False,
                    item_count=1,
                )
                await services.telegram_log_service.send_bot_error(
                    bot=context.bot,
                    title="Playlist item failed",
                    error=exc,
                    user_id=session.user_id,
                    chat_id=query_message.chat_id,
                    provider=provider.key,
                    action=action,
                    job_id=session.job_id,
                    extra_lines=[f"item_index={index}", f"item_title={entry.title}"],
                )
                await context.bot.send_message(
                    chat_id=query_message.chat_id,
                    text=(
                        f"⚠️ Bỏ qua <code>[{index}/{len(entries)}]</code>: "
                        f"<code>{escape_html(entry.title[:55])}</code>\n"
                        "Video này không tải được hoặc đang bị giới hạn."
                    ),
                    parse_mode=ParseMode.HTML,
                )
    finally:
        remove_tree(base_dir)

    icon = "✅" if failure_count == 0 else ("⚠️" if success_count > 0 else "❌")
    await _safe_edit(
        status_message,
        (
            f"{icon} <b>Hoàn tất tải playlist!</b>\n\n"
            f"📋 <code>{session.media_info.title[:70]}</code>\n"
            f"✅ Thành công: <code>{success_count}/{len(entries)}</code>\n"
            f"❌ Lỗi/bỏ qua: <code>{failure_count}/{len(entries)}</code>"
        ),
    )


def _playlist_progress_text(
    *,
    title: str,
    current_title: str,
    index: int,
    total: int,
    success_count: int,
    failure_count: int,
) -> str:
    if total <= 20:
        bar = "▓" * index + "░" * (total - index)
        progress = f"<code>[{bar}]</code>"
    else:
        pct = int(index / total * 100)
        progress = f"<code>{pct}%</code> ({index}/{total})"
    return (
        "📋 <b>Đang tải playlist...</b>\n\n"
        f"📁 <code>{title[:60]}</code>\n"
        f"📊 {progress}\n"
        f"🎬 <code>{current_title[:55]}</code>\n\n"
        f"✅ <code>{success_count}</code> thành công · ❌ <code>{failure_count}</code> lỗi"
    )


async def _send_session_expired(message: Message) -> None:
    await message.reply_text(
        (
            "⚠️ <b>Phiên làm việc đã hết hạn</b>\n\n"
            "Dữ liệu callback không còn trong store nữa.\n"
            "Vui lòng gửi lại link để tạo yêu cầu mới."
        ),
        parse_mode=ParseMode.HTML,
    )


async def _safe_edit(message: Message, text: str) -> None:
    try:
        await message.edit_text(text, parse_mode=ParseMode.HTML)
    except Exception:
        pass
