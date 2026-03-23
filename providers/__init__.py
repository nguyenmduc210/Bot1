from __future__ import annotations

from providers.base import BaseProvider
from providers.facebook import FacebookProvider
from providers.soundcloud import SoundCloudProvider
from providers.tiktok import TikTokProvider
from providers.youtube import YouTubeProvider
from services.cookie_store import CookieStore
from services.http_client import AsyncHTTPClient
from config import Settings


def build_providers(settings: Settings, http_client: AsyncHTTPClient, cookie_store: CookieStore) -> dict[str, BaseProvider]:
    providers = [
        YouTubeProvider(settings, http_client, cookie_store),
        FacebookProvider(settings, http_client, cookie_store),
        TikTokProvider(settings, http_client, cookie_store),
        SoundCloudProvider(settings, http_client, cookie_store),
    ]
    return {provider.key: provider for provider in providers}


def detect_provider(url: str, providers: dict[str, BaseProvider]) -> BaseProvider | None:
    for key in ("youtube", "facebook", "tiktok", "soundcloud"):
        provider = providers[key]
        if provider.supports(url):
            return provider
    return None
