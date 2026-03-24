from __future__ import annotations

import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from handlers.common import get_services
from logging_setup import log_extra
from utils.formatters import format_size


logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user = update.effective_user
    if not user or not update.effective_message:
        return
    await services.stats_store.mark_user_seen(user.id)
    logger.info("Command /start", extra=log_extra(user_id=user.id, action="/start", status="ok"))
    name = user.first_name or "bạn"
    await update.effective_message.reply_text(
        (
            f"👋 <b>Xin chào, {name}!</b>\n\n"
            "Tôi là bot tải media chuyên nghiệp, hỗ trợ các nền tảng:\n\n"
            "▸ 🎬 <b>TikTok</b> — Video không watermark, album ảnh, âm thanh gốc\n"
            "▸ 🎵 <b>SoundCloud</b> — Track đơn và playlist, ưu tiên âm thanh gốc\n"
            "▸ 📺 <b>YouTube</b> — Video, MP3, Playlist & Mix cá nhân hóa 🍪\n"
            "▸ 📹 <b>Facebook</b> — Video, Reels công khai, MP3, file gốc\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 <b>Cách dùng:</b> Chỉ cần dán link và gửi.\n"
            "❓ <b>Trợ giúp:</b> /help\n"
            "📊 <b>Thống kê:</b> /stats"
        ),
        parse_mode=ParseMode.HTML,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not user or not update.effective_message:
        return
    logger.info("Command /help", extra=log_extra(user_id=user.id, action="/help", status="ok"))
    await update.effective_message.reply_text(
        (
            "📖 <b>Hướng dẫn sử dụng chi tiết</b>\n\n"
            "<b>── Nền tảng được hỗ trợ ──</b>\n"
            "▸ <code>tiktok.com</code> · <code>vt.tiktok.com</code>\n"
            "▸ <code>soundcloud.com</code> · <code>on.soundcloud.com</code>\n"
            "▸ <code>youtube.com</code> · <code>youtu.be</code> · <code>m.youtube.com</code>\n"
            "▸ <code>facebook.com</code> · <code>fb.com</code> · <code>fb.watch</code>\n\n"
            "<b>── Định dạng xuất ──</b>\n"
            "▸ TikTok Video — MP4 không watermark, HD tối đa\n"
            "▸ TikTok Album — Toàn bộ ảnh trong bộ sưu tập\n"
            "▸ TikTok Nhạc — Ưu tiên âm thanh gốc tách từ video\n"
            "▸ SoundCloud — Ưu tiên âm thanh gốc, hỗ trợ playlist\n"
            "▸ YouTube Video — MP4 tối đa 1080p\n"
            "▸ YouTube Audio — MP3 320kbps, metadata nhúng\n"
            "▸ YouTube Playlist — Tải tối đa 50 video mỗi lần\n"
            "▸ YouTube Mix/Radio — Dùng cookie riêng của bạn nếu có\n"
            "▸ Facebook Video — MP4 tối đa 1080p\n"
            "▸ Facebook Audio — MP3 320kbps\n"
            "▸ MP4 File gốc — YouTube · Facebook · TikTok\n\n"
            "<b>── YouTube Mix & Cookie ──</b>\n"
            "YouTube Mix là danh sách cá nhân hóa theo tài khoản.\n"
            "Bot lưu cookie riêng từng người, không dùng chung.\n\n"
            "Cách thêm cookie:\n"
            "1. Cài extension <b>Get cookies.txt LOCALLY</b>\n"
            "2. Vào <code>youtube.com</code> khi đang đăng nhập\n"
            "3. Export file <code>cookies.txt</code>\n"
            "4. Gửi file đó trực tiếp cho bot\n\n"
            "🍪 /mycookie — xem trạng thái cookie của bạn\n"
            "🔐 /login [link] — thử xác minh YouTube bằng cookie hiện tại\n"
            "🗑️ /delcookie — xóa cookie\n\n"
            "<b>── Giới hạn kỹ thuật ──</b>\n"
            "▸ File ≤ 50 MB → gửi trực tiếp\n"
            "▸ File > 50 MB → tự động chia nhỏ\n"
            "▸ Album ảnh → tối đa 10 ảnh/nhóm\n"
            "▸ Playlist YouTube → tối đa 50 video\n"
            "▸ Facebook riêng tư/livestream → không hỗ trợ\n\n"
            "💡 Nếu link không hoạt động, hãy sao chép URL gốc từ ứng dụng."
        ),
        parse_mode=ParseMode.HTML,
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user = update.effective_user
    if not user or not update.effective_message:
        return
    snapshot = await services.stats_store.get_snapshot()
    started_at = context.application.bot_data["started_at"]
    uptime = datetime.now(timezone.utc) - started_at
    hours, remainder = divmod(int(uptime.total_seconds()), 3600)
    minutes = remainder // 60
    success_rate = (
        f"{(snapshot.success_count / snapshot.item_processed_count) * 100:.1f}%"
        if snapshot.item_processed_count
        else "N/A"
    )
    logger.info("Command /stats", extra=log_extra(user_id=user.id, action="/stats", status="ok"))
    await update.effective_message.reply_text(
        (
            "📊 <b>Thống kê bot</b>\n\n"
            f"⏱️ Thời gian hoạt động : <code>{hours}h {minutes:02d}m</code>\n"
            f"👥 User duy nhất       : <code>{snapshot.unique_users}</code>\n"
            f"📨 Request nhận        : <code>{snapshot.request_count}</code>\n"
            f"🧩 Item đã xử lý       : <code>{snapshot.item_processed_count}</code>\n"
            f"✅ Thành công          : <code>{snapshot.success_count}</code>\n"
            f"❌ Thất bại            : <code>{snapshot.failure_count}</code>\n"
            f"🎯 Tỷ lệ thành công    : <code>{success_rate}</code>\n"
            f"📦 Tổng dung lượng     : <code>{format_size(snapshot.total_bytes)}</code>\n\n"
            "Ghi chú:\n"
            "• <b>Request</b> = số yêu cầu người dùng gửi.\n"
            "• <b>Item</b> = số media thực xử lý, playlist được tính theo từng video."
        ),
        parse_mode=ParseMode.HTML,
    )


async def mycookie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user = update.effective_user
    if not user or not update.effective_message:
        return
    metadata = await services.cookie_store.get_cookie_metadata(user.id)
    logger.info("Command /mycookie", extra=log_extra(user_id=user.id, action="/mycookie", status="ok"))
    if metadata:
        updated = metadata.updated_at.astimezone().strftime("%d/%m/%Y %H:%M")
        await update.effective_message.reply_text(
            (
                "🍪 <b>Trạng thái Cookie YouTube của bạn</b>\n\n"
                f"✅ <code>{metadata.line_count}</code> mục · Cập nhật: <code>{updated}</code>\n\n"
                "YouTube Mix và playlist cá nhân hóa đã sẵn sàng.\n"
                "🔐 Kiểm tra đăng nhập: /login\n"
                "🗑️ Xóa cookie: /delcookie"
            ),
            parse_mode=ParseMode.HTML,
        )
        return
    await update.effective_message.reply_text(
        (
            "🍪 <b>Trạng thái Cookie YouTube của bạn</b>\n\n"
            "❌ Chưa có cookie.\n\n"
            "Cách thêm cookie:\n"
            "1. Cài extension <b>Get cookies.txt LOCALLY</b>\n"
            "2. Vào <code>youtube.com</code> khi đang đăng nhập\n"
            "3. Export file <code>cookies.txt</code>\n"
            "4. Gửi file đó cho bot"
        ),
        parse_mode=ParseMode.HTML,
    )


async def login_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user = update.effective_user
    if not user or not update.effective_message:
        return
    provider = services.providers["youtube"]
    url = " ".join(context.args).strip() if context.args else ""
    if url and not provider.supports(url):
        await update.effective_message.reply_text(
            "❌ <b>/login chỉ kiểm tra link YouTube.</b>\n\nDùng: <code>/login https://youtu.be/...</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    status = await update.effective_message.reply_text(
        (
            "🔐 <b>Đang kiểm tra quyền truy cập video YouTube bằng cookie...</b>"
            if url
            else "🔐 <b>Đang kiểm tra đăng nhập YouTube bằng cookie...</b>"
        ),
        parse_mode=ParseMode.HTML,
    )
    logger.info("Command /login", extra=log_extra(user_id=user.id, action="/login", status="check"))
    metadata = await services.cookie_store.get_cookie_metadata(user.id)
    if metadata is None:
        await status.edit_text(
            "❌ <b>Chưa có cookie YouTube.</b>\n\nGửi file <code>cookies.txt</code> trước rồi thử lại.",
            parse_mode=ParseMode.HTML,
        )
        return
    ok, message = await provider.check_login(user.id, url or None)
    await status.edit_text(
        ("✅ <b>Kiểm tra đăng nhập thành công</b>\n\n" if ok else "❌ <b>Kiểm tra đăng nhập thất bại</b>\n\n")
        + message
        + (
            ""
            if url
            else "\n\nMuốn kiểm tra sát thực tế tải video, dùng: <code>/login https://youtu.be/...</code>"
        ),
        parse_mode=ParseMode.HTML,
    )


async def delcookie_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    services = get_services(context)
    user = update.effective_user
    if not user or not update.effective_message:
        return
    removed = await services.cookie_store.delete_cookie(user.id)
    logger.info(
        "Command /delcookie",
        extra=log_extra(user_id=user.id, action="/delcookie", status="ok" if removed else "empty"),
    )
    if removed:
        await update.effective_message.reply_text(
            "🗑️ <b>Cookie đã được xóa thành công.</b>\n\nYouTube Mix sẽ quay về chế độ video đơn cho tới khi bạn gửi cookie mới.",
            parse_mode=ParseMode.HTML,
        )
        return
    await update.effective_message.reply_text(
        "ℹ️ Bạn chưa có cookie nào được lưu.",
        parse_mode=ParseMode.HTML,
    )
