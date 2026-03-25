from __future__ import annotations

from datetime import timedelta

from handlers.callbacks import _build_caption_messages, parse_callback_data, resolve_callback_route
from models import MediaInfo, MediaKind, Platform, SessionData, utcnow


def test_callback_action_routing_single() -> None:
    action, job_id = parse_callback_data("ytv:job123")
    route = resolve_callback_route(action)
    assert action == "ytv"
    assert job_id == "job123"
    assert route.is_playlist is False
    assert route.is_album is False


def test_callback_action_routing_playlist() -> None:
    action, job_id = parse_callback_data("ytpldoc:job999")
    route = resolve_callback_route(action)
    assert action == "ytpldoc"
    assert job_id == "job999"
    assert route.is_playlist is True
    assert route.is_album is False


def test_callback_action_routing_soundcloud_playlist() -> None:
    action, job_id = parse_callback_data("scplmus:job777")
    route = resolve_callback_route(action)
    assert action == "scplmus"
    assert job_id == "job777"
    assert route.is_playlist is True
    assert route.is_album is False


def test_callback_action_routing_album() -> None:
    action, job_id = parse_callback_data("img:job555")
    route = resolve_callback_route(action)
    assert route.is_album is True
    assert route.is_playlist is False


def test_callback_action_routing_caption() -> None:
    action, job_id = parse_callback_data("cap:job321")
    route = resolve_callback_route(action)
    assert action == "cap"
    assert job_id == "job321"
    assert route.is_album is False
    assert route.is_playlist is False


def test_build_caption_messages_splits_long_caption() -> None:
    now = utcnow()
    session = SessionData(
        job_id="cap-1",
        user_id=10,
        provider=Platform.TIKTOK,
        source_url="https://www.tiktok.com/@demo/video/1",
        media_info=MediaInfo(
            provider=Platform.TIKTOK,
            source_url="https://www.tiktok.com/@demo/video/1",
            title="Demo video",
            full_caption=("dong " * 1200).strip(),
            media_kind=MediaKind.VIDEO,
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=30),
    )

    messages = _build_caption_messages(session)

    assert len(messages) >= 2
    assert messages[0].startswith("📝 Captions 1/")
    assert all(len(message) < 4096 for message in messages)
