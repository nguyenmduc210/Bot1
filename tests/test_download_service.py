from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
import yt_dlp

from models import BotError, DownloadBackend, DownloadPlan, ErrorCode, MediaInfo, MediaKind, Platform, SendMethod, SessionData, utcnow
from services.download_service import DownloadService, _build_requested_format_retry_options


def _build_youtube_session(url: str) -> SessionData:
    now = utcnow()
    return SessionData(
        job_id="job-1",
        user_id=123,
        provider=Platform.YOUTUBE,
        source_url=url,
        media_info=MediaInfo(
            provider=Platform.YOUTUBE,
            source_url=url,
            title="Demo video",
            uploader="Demo channel",
            duration=180,
            media_kind=MediaKind.VIDEO,
            available_actions=["ytv", "yta", "ytdoc"],
        ),
        created_at=now,
        expires_at=now + timedelta(minutes=30),
    )


def test_retry_options_relax_youtube_video_format() -> None:
    plan = DownloadPlan(
        action="ytv",
        provider=Platform.YOUTUBE,
        backend=DownloadBackend.YT_DLP,
        send_method=SendMethod.VIDEO,
        source_url="https://youtube.com/watch?v=test",
        output_template="temp/media.%(ext)s",
        ydl_options={"format": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"},
    )
    options = _build_requested_format_retry_options(plan)
    assert options is not None
    assert options["format"] == "bestvideo*+bestaudio/best*"
    assert options["ignoreconfig"] is True


def test_retry_options_keep_audio_profile() -> None:
    plan = DownloadPlan(
        action="yta",
        provider=Platform.YOUTUBE,
        backend=DownloadBackend.YT_DLP,
        send_method=SendMethod.AUDIO,
        source_url="https://youtube.com/watch?v=test",
        output_template="temp/media.%(ext)s",
        ydl_options={"format": "bestaudio/best"},
    )
    options = _build_requested_format_retry_options(plan)
    assert options is not None
    assert options["format"] == "bestaudio/best"


def test_retry_options_keep_tiktok_audio_as_best_video_file() -> None:
    plan = DownloadPlan(
        action="mus",
        provider=Platform.TIKTOK,
        backend=DownloadBackend.YT_DLP,
        send_method=SendMethod.AUDIO,
        source_url="https://api.example/video.mp4",
        output_template="temp/media.%(ext)s",
        ydl_options={"format": "best"},
    )
    options = _build_requested_format_retry_options(plan)
    assert options is not None
    assert options["format"] == "best"


def test_youtube_plan_contains_cobalt_request(providers, tmp_path: Path) -> None:
    provider = providers["youtube"]
    session = _build_youtube_session("https://youtube.com/watch?v=test")

    video_plan = provider.build_download_options(action="ytv", session=session, output_dir=tmp_path / "video")
    assert video_plan.cobalt_request is not None
    assert video_plan.cobalt_request["url"] == session.source_url
    assert video_plan.cobalt_request["youtubeVideoContainer"] == "mp4"
    assert video_plan.cobalt_request["videoQuality"] == "1080"

    audio_plan = provider.build_download_options(action="yta", session=session, output_dir=tmp_path / "audio")
    assert audio_plan.cobalt_request is not None
    assert audio_plan.cobalt_request["downloadMode"] == "audio"
    assert audio_plan.cobalt_request["audioFormat"] == "mp3"
    assert audio_plan.cobalt_request["audioBitrate"] == "320"


def test_download_service_falls_back_to_cobalt_when_ytdlp_fails(
    settings,
    http_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DownloadService(http_client, settings, max_concurrent_downloads=1)
    plan = DownloadPlan(
        action="ytv",
        provider=Platform.YOUTUBE,
        backend=DownloadBackend.YT_DLP,
        send_method=SendMethod.VIDEO,
        source_url="https://youtube.com/watch?v=test",
        output_template=str(tmp_path / "media.%(ext)s"),
        ydl_options={"format": "best"},
        cobalt_request={"url": "https://youtube.com/watch?v=test", "videoQuality": "1080"},
        allowed_extensions=(".mp4", ".mkv", ".webm"),
    )

    def fake_run_ytdlp_sync(_ydl_options: dict, _url: str | None) -> None:
        raise yt_dlp.utils.DownloadError("extractor crashed")

    async def fake_post_json(url: str, *, json_body: dict, headers=None, timeout_seconds=None) -> dict:
        assert url == settings.cobalt_api_url
        assert json_body == plan.cobalt_request
        assert headers is not None
        return {
            "status": "redirect",
            "url": "https://cdn.example/fallback.mp4",
            "filename": "fallback video.mp4",
        }

    async def fake_download_file(url: str, destination: Path, *, headers=None, timeout_seconds=None) -> int:
        assert url == "https://cdn.example/fallback.mp4"
        destination.write_bytes(b"video-data")
        return destination.stat().st_size

    monkeypatch.setattr("services.download_service._run_ytdlp_sync", fake_run_ytdlp_sync)
    monkeypatch.setattr(http_client, "post_json", fake_post_json)
    monkeypatch.setattr(http_client, "download_file", fake_download_file)

    file_path = asyncio.run(service._download_with_ytdlp(plan))

    assert file_path.name == "fallback video.mp4"
    assert file_path.read_bytes() == b"video-data"


def test_download_service_preserves_login_required_error(
    settings,
    http_client,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DownloadService(http_client, settings, max_concurrent_downloads=1)
    plan = DownloadPlan(
        action="yta",
        provider=Platform.YOUTUBE,
        backend=DownloadBackend.YT_DLP,
        send_method=SendMethod.AUDIO,
        source_url="https://youtube.com/watch?v=test",
        output_template=str(tmp_path / "media.%(ext)s"),
        ydl_options={"format": "bestaudio/best"},
        cobalt_request={"url": "https://youtube.com/watch?v=test", "downloadMode": "audio"},
        allowed_extensions=(".mp3", ".m4a", ".webm"),
    )

    def fake_run_ytdlp_sync(_ydl_options: dict, _url: str | None) -> None:
        raise yt_dlp.utils.DownloadError("Sign in to confirm you're not a bot")

    async def unexpected_post_json(*args, **kwargs) -> dict:
        raise AssertionError("Cobalt fallback should not run for login-required errors")

    monkeypatch.setattr("services.download_service._run_ytdlp_sync", fake_run_ytdlp_sync)
    monkeypatch.setattr(http_client, "post_json", unexpected_post_json)

    with pytest.raises(BotError) as exc_info:
        asyncio.run(service._download_with_ytdlp(plan))

    assert exc_info.value.code == ErrorCode.AGE_LOGIN_REQUIRED
