from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

from models import DownloadBackend, MediaInfo, MediaKind, Platform, SendMethod, SessionData, utcnow


def _build_tiktok_session(url: str) -> SessionData:
    now = utcnow()
    return SessionData(
        job_id="job-tiktok-1",
        user_id=123,
        provider=Platform.TIKTOK,
        source_url=url,
        media_info=MediaInfo(
            provider=Platform.TIKTOK,
            source_url=url,
            title="Demo TikTok",
            media_kind=MediaKind.VIDEO,
            available_actions=["vid", "mus", "tkdoc"],
            extra={
                "id": "721234567890",
                "play": "https://cdn.example/video.mp4",
                "music": "https://cdn.example/music.mp3",
                "original_url": url,
            },
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=30),
    )


def test_tiktok_audio_plan_uses_video_url_instead_of_music_url(providers, tmp_path: Path) -> None:
    provider = providers["tiktok"]
    session = _build_tiktok_session("https://www.tiktok.com/@demo/video/721234567890")

    plan = provider.build_download_options(action="mus", session=session, output_dir=tmp_path / "audio")

    assert plan.backend == DownloadBackend.DIRECT
    assert plan.send_method == SendMethod.AUDIO
    assert plan.source_url == session.media_info.extra["play"]
    assert plan.output_path == (tmp_path / "audio" / "media.mp4")
    assert plan.converted_output_path == (tmp_path / "audio" / "media.m4a")
    assert plan.cobalt_request is None
    assert plan.headers["Referer"] == "https://www.tiktok.com/"


def test_tiktok_extract_info_keeps_audio_action_without_music_link(providers, monkeypatch) -> None:
    provider = providers["tiktok"]

    async def fake_extract(url: str) -> dict:
        return {
            "id": "721234567890",
            "title": "Demo TikTok",
            "cover": "https://cdn.example/cover.jpg",
            "play": "https://cdn.example/video.mp4",
            "music": None,
            "images": [],
            "source_name": "test",
        }

    monkeypatch.setattr(provider, "_extract_tiktok_data", fake_extract)

    info = asyncio.run(provider.extract_info("https://www.tiktok.com/@demo/video/721234567890", user_id=123))

    assert info.media_kind == MediaKind.VIDEO
    assert info.available_actions == ["vid", "mus", "tkdoc"]
