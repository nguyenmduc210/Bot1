from __future__ import annotations

from dataclasses import replace

from providers.youtube import YouTubeProvider
from services.cookie_store import CookieStore
from services.http_client import AsyncHTTPClient


def test_youtube_cookie_resolution_prefers_user_cookie(settings, tmp_path) -> None:
    global_cookie = tmp_path / "global.txt"
    global_cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    user_cookie_dir = settings.cookies_dir
    user_cookie = user_cookie_dir / "123.txt"
    user_cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    settings = replace(settings, youtube_global_cookie_file=global_cookie)
    cookie_store = CookieStore(settings.sqlite_path, settings.cookies_dir)
    http_client = AsyncHTTPClient(timeout_seconds=5.0, max_retries=1, backoff_seconds=0.1)
    provider = YouTubeProvider(settings, http_client, cookie_store)
    path, scope = provider._resolve_cookie_path(123)
    assert scope == "user"
    assert path == user_cookie


def test_youtube_cookie_resolution_falls_back_to_global(settings, tmp_path) -> None:
    global_cookie = tmp_path / "global.txt"
    global_cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    settings = replace(settings, youtube_global_cookie_file=global_cookie)
    cookie_store = CookieStore(settings.sqlite_path, settings.cookies_dir)
    http_client = AsyncHTTPClient(timeout_seconds=5.0, max_retries=1, backoff_seconds=0.1)
    provider = YouTubeProvider(settings, http_client, cookie_store)
    path, scope = provider._resolve_cookie_path(456)
    assert scope == "global"
    assert path == global_cookie
