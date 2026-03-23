from __future__ import annotations

from providers import detect_provider


def test_detect_platform_youtube(providers) -> None:
    provider = detect_provider("https://www.youtube.com/watch?v=abc123", providers)
    assert provider is not None
    assert provider.key == "youtube"


def test_detect_platform_facebook(providers) -> None:
    provider = detect_provider("https://www.facebook.com/reel/12345", providers)
    assert provider is not None
    assert provider.key == "facebook"


def test_detect_platform_tiktok(providers) -> None:
    provider = detect_provider("https://vt.tiktok.com/ZShTest/", providers)
    assert provider is not None
    assert provider.key == "tiktok"


def test_detect_platform_soundcloud(providers) -> None:
    provider = detect_provider("https://soundcloud.com/artist/track", providers)
    assert provider is not None
    assert provider.key == "soundcloud"


def test_detect_platform_unknown(providers) -> None:
    provider = detect_provider("https://example.com/file.mp4", providers)
    assert provider is None
