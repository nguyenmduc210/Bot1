from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from config import load_settings
from handlers.callbacks import handle_button
from handlers.commands import delcookie_command, help_command, login_command, mycookie_command, start, stats_command
from handlers.messages import handle_document, handle_message
from logging_setup import log_extra, setup_logging
from providers import build_providers
from services.container import AppServices
from services.cookie_store import CookieStore
from services.download_service import DownloadService
from services.http_client import AsyncHTTPClient
from services.media_sender import MediaSender
from services.rate_limiter import RateLimiter
from services.session_store import SessionStore
from services.stats_store import StatsStore
from services.telegram_log_service import TelegramLogService


logger = logging.getLogger(__name__)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception", exc_info=context.error)
    services = context.application.bot_data.get("services")
    if services is not None and isinstance(update, Update) and context.error is not None:
        await services.telegram_log_service.send_exception(
            bot=context.bot,
            title="Unhandled application exception",
            error=context.error,
            user_id=update.effective_user.id if update.effective_user else None,
            chat_id=update.effective_chat.id if update.effective_chat else None,
            extra_lines=[f"update_type={type(update).__name__}"],
        )
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            (
                "⚠️ <b>Lỗi hệ thống nội bộ</b>\n\n"
                "Bot gặp sự cố không mong muốn trong quá trình xử lý yêu cầu.\n"
                "Sự cố đã được ghi log ở server. Vui lòng thử lại sau."
            ),
            parse_mode=ParseMode.HTML,
        )


def build_services() -> AppServices:
    settings = load_settings()
    http_client = AsyncHTTPClient(
        timeout_seconds=settings.http_timeout_seconds,
        max_retries=settings.http_max_retries,
        backoff_seconds=settings.http_backoff_seconds,
    )
    session_store = SessionStore(settings.sqlite_path, settings.session_ttl_seconds)
    cookie_store = CookieStore(settings.sqlite_path, settings.cookies_dir)
    stats_store = StatsStore(settings.sqlite_path)
    rate_limiter = RateLimiter(settings.rate_limit_seconds)
    download_service = DownloadService(
        http_client,
        settings,
        max_concurrent_downloads=settings.max_concurrent_downloads,
    )
    media_sender = MediaSender(
        telegram_file_limit_bytes=settings.telegram_file_limit_bytes,
        upload_read_timeout_seconds=settings.upload_read_timeout_seconds,
    )
    telegram_log_service = TelegramLogService(
        chat_id=settings.telegram_log_chat_id,
        message_thread_id=settings.telegram_log_thread_id,
    )
    providers = build_providers(settings, http_client, cookie_store)
    return AppServices(
        settings=settings,
        session_store=session_store,
        cookie_store=cookie_store,
        stats_store=stats_store,
        rate_limiter=rate_limiter,
        http_client=http_client,
        download_service=download_service,
        media_sender=media_sender,
        telegram_log_service=telegram_log_service,
        providers=providers,
    )


def build_application(services: AppServices):
    application = (
        ApplicationBuilder()
        .token(services.settings.bot_token)
        .concurrent_updates(True)
        .build()
    )
    application.bot_data["services"] = services
    application.bot_data["started_at"] = datetime.now(timezone.utc)

    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("mycookie", mycookie_command))
    application.add_handler(CommandHandler("login", login_command))
    application.add_handler(CommandHandler("delcookie", delcookie_command))
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(handle_button))
    return application


def main() -> None:
    services = build_services()
    setup_logging(services.settings.log_level)
    logger.info(
        "Starting Telegram media bot",
        extra=log_extra(status="boot"),
    )
    application = build_application(services)
    try:
        application.run_polling()
    finally:
        asyncio.run(services.http_client.close())


if __name__ == "__main__":
    main()
