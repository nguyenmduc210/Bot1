from __future__ import annotations

from pathlib import Path

from providers.common import build_download_base_options, build_extract_options


def test_extract_options_ignore_global_ytdlp_config() -> None:
    options = build_extract_options()
    assert options["ignoreconfig"] is False
    assert options["format"] == "best/bestvideo+bestaudio"


def test_extract_options_flat_playlist_does_not_force_format() -> None:
    options = build_extract_options(extract_flat=True)
    assert "format" not in options


def test_extract_options_can_use_runtime_config() -> None:
    options = build_extract_options(ignore_config=False)
    assert options["ignoreconfig"] is False


def test_download_options_ignore_global_ytdlp_config(tmp_path: Path) -> None:
    options = build_download_base_options(output_dir=tmp_path)
    assert options["ignoreconfig"] is False
