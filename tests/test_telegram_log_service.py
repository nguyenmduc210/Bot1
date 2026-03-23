from __future__ import annotations

import asyncio

from models import BotError, ErrorCode
from services.telegram_log_service import TelegramLogService


class _FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def send_message(self, **kwargs) -> None:
        self.messages.append(kwargs)


def test_telegram_log_service_skips_when_disabled() -> None:
    service = TelegramLogService(chat_id=None)
    bot = _FakeBot()

    asyncio.run(
        service.send_bot_error(
            bot=bot,
            title="Download failed",
            error=BotError(ErrorCode.DOWNLOAD_FAILED, "public", "internal"),
        )
    )

    assert bot.messages == []


def test_telegram_log_service_sends_bot_error_message() -> None:
    service = TelegramLogService(chat_id=-100123, message_thread_id=77)
    bot = _FakeBot()

    asyncio.run(
        service.send_bot_error(
            bot=bot,
            title="Download failed",
            error=BotError(ErrorCode.DOWNLOAD_FAILED, "public", "internal detail"),
            user_id=123,
            chat_id=456,
            provider="tiktok",
            action="mus",
            job_id="job-1",
            extra_lines=["url=https://example.test/video"],
        )
    )

    assert len(bot.messages) == 1
    payload = bot.messages[0]
    assert payload["chat_id"] == -100123
    assert payload["message_thread_id"] == 77
    assert payload["parse_mode"] == "HTML"
    assert "Download failed" in payload["text"]
    assert "internal detail" in payload["text"]
    assert "provider: <code>tiktok</code>" in payload["text"]
