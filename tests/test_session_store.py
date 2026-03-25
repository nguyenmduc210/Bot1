from __future__ import annotations

import asyncio
from datetime import timedelta

from models import MediaInfo, MediaKind, Platform, SessionData, utcnow
from services.session_store import SessionStore


def test_session_ttl_cleanup(tmp_path) -> None:
    store = SessionStore(tmp_path / "state.sqlite3", default_ttl_seconds=1)
    session = SessionData(
        job_id="abc123",
        user_id=10,
        provider=Platform.YOUTUBE,
        source_url="https://youtube.com/watch?v=1",
        media_info=MediaInfo(
            provider=Platform.YOUTUBE,
            source_url="https://youtube.com/watch?v=1",
            title="Video",
            full_caption="Mo ta day du",
            media_kind=MediaKind.VIDEO,
        ),
        created_at=utcnow() - timedelta(seconds=5),
        expires_at=utcnow() - timedelta(seconds=1),
    )
    asyncio.run(store.create_session(session))
    loaded = asyncio.run(store.get_session("abc123", user_id=10))
    assert loaded is None


def test_session_store_roundtrips_full_caption(tmp_path) -> None:
    store = SessionStore(tmp_path / "state.sqlite3", default_ttl_seconds=60)
    now = utcnow()
    session = SessionData(
        job_id="cap456",
        user_id=11,
        provider=Platform.TIKTOK,
        source_url="https://www.tiktok.com/@demo/video/1",
        media_info=MediaInfo(
            provider=Platform.TIKTOK,
            source_url="https://www.tiktok.com/@demo/video/1",
            title="Video",
            full_caption="Caption day du cua video",
            media_kind=MediaKind.VIDEO,
        ),
        created_at=now,
        expires_at=now + timedelta(seconds=60),
    )

    asyncio.run(store.create_session(session))
    loaded = asyncio.run(store.get_session("cap456", user_id=11))

    assert loaded is not None
    assert loaded.media_info.full_caption == "Caption day du cua video"
