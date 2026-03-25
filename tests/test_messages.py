from __future__ import annotations

from handlers.messages import _build_keyboard
from models import MediaInfo, MediaKind, Platform


def test_preview_keyboard_shows_caption_button_when_full_caption_exists() -> None:
    media_info = MediaInfo(
        provider=Platform.TIKTOK,
        source_url="https://www.tiktok.com/@demo/video/1",
        title="Demo",
        full_caption="Day la caption day du",
        media_kind=MediaKind.VIDEO,
        available_actions=["vid", "mus", "tkdoc"],
    )

    keyboard = _build_keyboard(media_info, "job123")

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.callback_data == "cap:job123" for button in buttons)


def test_preview_keyboard_hides_caption_button_for_playlist() -> None:
    media_info = MediaInfo(
        provider=Platform.YOUTUBE,
        source_url="https://www.youtube.com/playlist?list=PL123",
        title="Demo playlist",
        full_caption="Khong can hien o day",
        media_kind=MediaKind.PLAYLIST,
        is_playlist=True,
        available_actions=["ytplv", "ytpla", "ytpldoc"],
    )

    keyboard = _build_keyboard(media_info, "job456")

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert all(button.callback_data != "cap:job456" for button in buttons)
