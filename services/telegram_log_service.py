from __future__ import annotations

import logging
import traceback

from telegram import Bot
from telegram.constants import ParseMode

from models import BotError
from utils.formatters import ellipsize, escape_html


logger = logging.getLogger(__name__)
_MAX_MESSAGE_LENGTH = 4000
_MAX_DETAIL_LENGTH = 1600


class TelegramLogService:
    def __init__(self, *, chat_id: int | None, message_thread_id: int | None = None) -> None:
        self.chat_id = chat_id
        self.message_thread_id = message_thread_id

    @property
    def enabled(self) -> bool:
        return self.chat_id is not None

    async def send_bot_error(
        self,
        *,
        bot: Bot,
        title: str,
        error: BotError,
        user_id: int | None = None,
        chat_id: int | None = None,
        provider: str | None = None,
        action: str | None = None,
        job_id: str | None = None,
        extra_lines: list[str] | None = None,
    ) -> None:
        lines = [
            f"🚨 <b>{escape_html(title)}</b>",
            f"• code: <code>{escape_html(error.code.value)}</code>",
            f"• user_message: <code>{escape_html(error.user_message)}</code>",
            f"• internal: <code>{escape_html(_shorten(error.internal_message, _MAX_DETAIL_LENGTH))}</code>",
        ]
        lines.extend(_context_lines(
            user_id=user_id,
            chat_id=chat_id,
            provider=provider,
            action=action,
            job_id=job_id,
        ))
        if extra_lines:
            lines.extend(f"• {escape_html(_shorten(line, 300))}" for line in extra_lines if line)
        await self._send_lines(bot=bot, lines=lines)

    async def send_exception(
        self,
        *,
        bot: Bot,
        title: str,
        error: Exception,
        user_id: int | None = None,
        chat_id: int | None = None,
        provider: str | None = None,
        action: str | None = None,
        job_id: str | None = None,
        extra_lines: list[str] | None = None,
    ) -> None:
        detail = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        lines = [
            f"🔥 <b>{escape_html(title)}</b>",
            f"• type: <code>{escape_html(type(error).__name__)}</code>",
            f"• detail: <code>{escape_html(_shorten(detail, _MAX_DETAIL_LENGTH))}</code>",
        ]
        lines.extend(_context_lines(
            user_id=user_id,
            chat_id=chat_id,
            provider=provider,
            action=action,
            job_id=job_id,
        ))
        if extra_lines:
            lines.extend(f"• {escape_html(_shorten(line, 300))}" for line in extra_lines if line)
        await self._send_lines(bot=bot, lines=lines)

    async def _send_lines(self, *, bot: Bot, lines: list[str]) -> None:
        if not self.enabled or self.chat_id is None:
            return
        text = "\n".join(lines)
        text = _shorten(text, _MAX_MESSAGE_LENGTH)
        try:
            await bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=ParseMode.HTML,
                message_thread_id=self.message_thread_id,
                disable_web_page_preview=True,
            )
        except Exception:
            logger.exception("Telegram log delivery failed")


def _context_lines(
    *,
    user_id: int | None,
    chat_id: int | None,
    provider: str | None,
    action: str | None,
    job_id: str | None,
) -> list[str]:
    lines: list[str] = []
    if user_id is not None:
        lines.append(f"• user_id: <code>{user_id}</code>")
    if chat_id is not None:
        lines.append(f"• chat_id: <code>{chat_id}</code>")
    if provider:
        lines.append(f"• provider: <code>{escape_html(provider)}</code>")
    if action:
        lines.append(f"• action: <code>{escape_html(action)}</code>")
    if job_id:
        lines.append(f"• job_id: <code>{escape_html(job_id)}</code>")
    return lines


def _shorten(value: str | None, max_length: int) -> str:
    return ellipsize((value or "").replace("\r", " ").replace("\n", " | "), max_length)
