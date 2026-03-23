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
            media_kind=MediaKind.VIDEO,
        ),
        created_at=utcnow() - timedelta(seconds=5),
        expires_at=utcnow() - timedelta(seconds=1),
    )
    asyncio.run(store.create_session(session))
    loaded = asyncio.run(store.get_session("abc123", user_id=10))
    assert loaded is None
