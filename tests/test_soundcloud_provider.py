from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from models import DownloadBackend, MediaInfo, MediaKind, Platform, PlaylistEntry, SendMethod, SessionData, utcnow


def _build_soundcloud_playlist_session(url: str) -> SessionData:
    now = utcnow()
    return SessionData(
        job_id="job-sc-1",
        user_id=123,
        provider=Platform.SOUNDCLOUD,
        source_url=url,
        media_info=MediaInfo(
            provider=Platform.SOUNDCLOUD,
            source_url=url,
            title="Demo Set",
            uploader="Demo Artist",
            media_kind=MediaKind.PLAYLIST,
            is_playlist=True,
            total_count=2,
            available_actions=["scplmus"],
            entries=[
                PlaylistEntry(id="1", title="Track 1", url="https://soundcloud.com/demo/track-1", duration=120),
                PlaylistEntry(id="2", title="Track 2", url="https://soundcloud.com/demo/track-2", duration=180),
            ],
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=30),
    )


def test_soundcloud_playlist_extract_info(providers, monkeypatch) -> None:
    provider = providers["soundcloud"]

    def fake_extract(url: str, max_videos: int) -> dict:
        assert max_videos > 0
        return {
            "webpage_url": url,
            "title": "Demo Set",
            "uploader": "Demo Artist",
            "thumbnail": "https://cdn.example/cover.jpg",
            "playlist_count": 2,
            "entries": [
                {
                    "id": "1",
                    "title": "Track 1",
                    "url": "soundcloud:tracks:1",
                    "webpage_url": "https://soundcloud.com/demo/track-1",
                    "duration": 120,
                },
                {
                    "id": "2",
                    "title": "Track 2",
                    "url": "soundcloud:tracks:2",
                    "webpage_url": "https://soundcloud.com/demo/track-2",
                    "duration": 180,
                },
            ],
        }

    monkeypatch.setattr("providers.soundcloud._extract_soundcloud_info_sync", fake_extract)

    info = asyncio.run(provider.extract_info("https://soundcloud.com/demo/sets/set-1", user_id=123))

    assert info.media_kind == MediaKind.PLAYLIST
    assert info.available_actions == ["scplmus"]
    assert len(info.entries) == 2
    assert info.total_count == 2
    assert info.entries[0].url == "https://soundcloud.com/demo/track-1"


def test_soundcloud_playlist_plan_uses_entry_url_and_keeps_original_audio(providers, tmp_path: Path) -> None:
    provider = providers["soundcloud"]
    session = _build_soundcloud_playlist_session("https://soundcloud.com/demo/sets/set-1")

    plan = provider.build_download_options(
        action="scplmus",
        session=session,
        output_dir=tmp_path / "audio",
        item_index=1,
    )

    assert plan.backend == DownloadBackend.YT_DLP
    assert plan.send_method == SendMethod.AUDIO
    assert plan.source_url == "https://soundcloud.com/demo/track-2"
    assert plan.ydl_options["format"] == "bestaudio/best"
    assert plan.ydl_options["postprocessors"] == []
    assert ".mp4" in plan.allowed_extensions
    assert "Âm thanh gốc" in plan.caption
