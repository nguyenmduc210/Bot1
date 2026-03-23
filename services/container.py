from __future__ import annotations

from dataclasses import dataclass

from config import Settings
from providers.base import BaseProvider
from services.cookie_store import CookieStore
from services.download_service import DownloadService
from services.http_client import AsyncHTTPClient
from services.media_sender import MediaSender
from services.rate_limiter import RateLimiter
from services.session_store import SessionStore
from services.stats_store import StatsStore
from services.telegram_log_service import TelegramLogService


@dataclass(slots=True)
class AppServices:
    settings: Settings
    session_store: SessionStore
    cookie_store: CookieStore
    stats_store: StatsStore
    rate_limiter: RateLimiter
    http_client: AsyncHTTPClient
    download_service: DownloadService
    media_sender: MediaSender
    telegram_log_service: TelegramLogService
    providers: dict[str, BaseProvider]
