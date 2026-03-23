from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import Settings
from providers.facebook import FacebookProvider
from providers.soundcloud import SoundCloudProvider
from providers.tiktok import TikTokProvider
from providers.youtube import YouTubeProvider
from services.cookie_store import CookieStore
from services.http_client import AsyncHTTPClient


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    data_dir = tmp_path / "data"
    cookies_dir = data_dir / "cookies"
    temp_root = data_dir / "tmp"
    sqlite_path = data_dir / "state.sqlite3"
    data_dir.mkdir(parents=True, exist_ok=True)
    cookies_dir.mkdir(parents=True, exist_ok=True)
    temp_root.mkdir(parents=True, exist_ok=True)
    return Settings(
        bot_token="test-token",
        base_dir=tmp_path,
        data_dir=data_dir,
        cookies_dir=cookies_dir,
        temp_root=temp_root,
        sqlite_path=sqlite_path,
        telegram_file_limit_bytes=49 * 1024 * 1024,
        session_ttl_seconds=1800,
        rate_limit_seconds=8.0,
        max_concurrent_downloads=2,
        max_playlist_videos=50,
        cookie_max_size_bytes=2 * 1024 * 1024,
        upload_read_timeout_seconds=180,
        http_timeout_seconds=30.0,
        http_max_retries=2,
        http_backoff_seconds=0.1,
        tiktok_primary_api="https://tikwm.com/api/",
        tiktok_fallback_api="https://api.douyin.wtf/api/hybrid/video_data",
        cobalt_api_url="https://cobalt.example",
        cobalt_api_key=None,
        cobalt_bearer_token=None,
        youtube_global_cookie_file=None,
        facebook_cookie_file=None,
        ytdlp_ignore_config=True,
        youtube_player_clients=("android", "web"),
        youtube_skip=("dash", "hls"),
        log_level="INFO",
        telegram_log_chat_id=None,
        telegram_log_thread_id=None,
    )


@pytest.fixture()
def cookie_store(settings: Settings) -> CookieStore:
    return CookieStore(settings.sqlite_path, settings.cookies_dir)


@pytest.fixture()
def http_client() -> AsyncHTTPClient:
    client = AsyncHTTPClient(timeout_seconds=5.0, max_retries=1, backoff_seconds=0.01)
    yield client
    asyncio.run(client.close())


@pytest.fixture()
def providers(settings: Settings, cookie_store: CookieStore, http_client: AsyncHTTPClient):
    return {
        "youtube": YouTubeProvider(settings, http_client, cookie_store),
        "facebook": FacebookProvider(settings, http_client, cookie_store),
        "tiktok": TikTokProvider(settings, http_client, cookie_store),
        "soundcloud": SoundCloudProvider(settings, http_client, cookie_store),
    }
