from __future__ import annotations

from models import ErrorCode
from providers.youtube import _map_ytdlp_error


def test_youtube_not_a_bot_error_maps_to_cookie_required() -> None:
    error = _map_ytdlp_error(
        Exception(
            "Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies for the authentication."
        )
    )
    assert error.code == ErrorCode.AGE_LOGIN_REQUIRED
    assert "cookies.txt" in error.user_message
