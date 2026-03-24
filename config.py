from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

BOT_TOKEN = ""
TELEGRAM_LOG_CHAT_ID = 
TELEGRAM_LOG_THREAD_ID = ""
YTDLP_IGNORE_CONFIG = False
YOUTUBE_PLAYER_CLIENTS = ("android", "web")
YOUTUBE_SKIP = ("dash", "hls")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    parts = tuple(item.strip() for item in value.split(",") if item.strip())
    return parts or default


def _optional_path(name: str) -> Path | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return Path(value).expanduser().resolve()


def _optional_str(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None


def _optional_int(name: str) -> int | None:
    value = os.getenv(name, "").strip()
    if not value:
        return None
    return int(value)


def _config_optional_int(value: int | str | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text)


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str
    base_dir: Path
    data_dir: Path
    cookies_dir: Path
    temp_root: Path
    sqlite_path: Path
    telegram_file_limit_bytes: int
    session_ttl_seconds: int
    rate_limit_seconds: float
    max_concurrent_downloads: int
    max_playlist_videos: int
    cookie_max_size_bytes: int
    upload_read_timeout_seconds: int
    http_timeout_seconds: float
    http_max_retries: int
    http_backoff_seconds: float
    tiktok_primary_api: str
    tiktok_fallback_api: str
    cobalt_api_url: str | None
    cobalt_api_key: str | None
    cobalt_bearer_token: str | None
    youtube_global_cookie_file: Path | None
    facebook_cookie_file: Path | None
    ytdlp_ignore_config: bool
    youtube_player_clients: tuple[str, ...]
    youtube_skip: tuple[str, ...]
    log_level: str
    telegram_log_chat_id: int | None
    telegram_log_thread_id: int | None

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self.temp_root.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    bot_token = BOT_TOKEN.strip() or os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise RuntimeError("Thiếu BOT_TOKEN trong config.py. Dán token trực tiếp vào biến BOT_TOKEN rồi chạy lại.")

    base_dir = Path(__file__).resolve().parent
    data_dir = Path(os.getenv("DATA_DIR", base_dir / "data")).expanduser().resolve()
    cookies_dir = Path(os.getenv("COOKIES_DIR", data_dir / "user_cookies")).expanduser().resolve()
    temp_root = Path(os.getenv("TEMP_ROOT", data_dir / "tmp")).expanduser().resolve()
    sqlite_path = Path(os.getenv("SQLITE_PATH", data_dir / "bot_state.sqlite3")).expanduser().resolve()

    settings = Settings(
        bot_token=bot_token,
        base_dir=base_dir,
        data_dir=data_dir,
        cookies_dir=cookies_dir,
        temp_root=temp_root,
        sqlite_path=sqlite_path,
        telegram_file_limit_bytes=_env_int("TELEGRAM_FILE_LIMIT_BYTES", 49 * 1024 * 1024),
        session_ttl_seconds=_env_int("SESSION_TTL_SECONDS", 1800),
        rate_limit_seconds=_env_float("RATE_LIMIT_SECONDS", 8.0),
        max_concurrent_downloads=_env_int("MAX_CONCURRENT_DOWNLOADS", 3),
        max_playlist_videos=_env_int("MAX_PLAYLIST_VIDEOS", 50),
        cookie_max_size_bytes=_env_int("COOKIE_MAX_SIZE_BYTES", 2 * 1024 * 1024),
        upload_read_timeout_seconds=_env_int("UPLOAD_READ_TIMEOUT_SECONDS", 180),
        http_timeout_seconds=_env_float("HTTP_TIMEOUT_SECONDS", 30.0),
        http_max_retries=_env_int("HTTP_MAX_RETRIES", 3),
        http_backoff_seconds=_env_float("HTTP_BACKOFF_SECONDS", 1.5),
        tiktok_primary_api=os.getenv("TIKTOK_PRIMARY_API", "https://tikwm.com/api/"),
        tiktok_fallback_api=os.getenv(
            "TIKTOK_FALLBACK_API",
            "https://api.douyin.wtf/api/hybrid/video_data",
        ),
        cobalt_api_url=_optional_str("COBALT_API_URL") or "https://api.cobalt.tools",
        cobalt_api_key=_optional_str("COBALT_API_KEY"),
        cobalt_bearer_token=_optional_str("COBALT_BEARER_TOKEN"),
        youtube_global_cookie_file=_optional_path("YT_COOKIES_FILE"),
        facebook_cookie_file=_optional_path("FB_COOKIES_FILE"),
        ytdlp_ignore_config=YTDLP_IGNORE_CONFIG,
        youtube_player_clients=YOUTUBE_PLAYER_CLIENTS,
        youtube_skip=YOUTUBE_SKIP,
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        telegram_log_chat_id=(
            _config_optional_int(TELEGRAM_LOG_CHAT_ID)
            if _config_optional_int(TELEGRAM_LOG_CHAT_ID) is not None
            else _optional_int("TELEGRAM_LOG_CHAT_ID")
        ),
        telegram_log_thread_id=(
            _config_optional_int(TELEGRAM_LOG_THREAD_ID)
            if _config_optional_int(TELEGRAM_LOG_THREAD_ID) is not None
            else _optional_int("TELEGRAM_LOG_THREAD_ID")
        ),
    )
    settings.ensure_directories()
    return settings
