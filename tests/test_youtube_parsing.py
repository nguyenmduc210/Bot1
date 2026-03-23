from __future__ import annotations

from providers.youtube import get_playlist_id, is_mix_playlist, is_regular_playlist


def test_get_playlist_id() -> None:
    url = "https://www.youtube.com/watch?v=abc123&list=PLXYZ987"
    assert get_playlist_id(url) == "PLXYZ987"


def test_detect_mix_playlist() -> None:
    assert is_mix_playlist("RDMM")
    assert is_mix_playlist("RDMIX123")
    assert not is_mix_playlist("PL123456")


def test_detect_regular_playlist() -> None:
    assert is_regular_playlist("https://www.youtube.com/playlist?list=PL123456")
    assert not is_regular_playlist("https://www.youtube.com/watch?v=abc&list=RDMM")
