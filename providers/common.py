from __future__ import annotations

from pathlib import Path
from typing import Any

from imageio_ffmpeg import get_ffmpeg_exe


def best_thumbnail(info: dict[str, Any]) -> str | None:
    thumbnail = info.get("thumbnail")
    thumbnails = info.get("thumbnails") or []
    if thumbnails:
        best = max(
            thumbnails,
            key=lambda item: (item.get("width") or 0) * (item.get("height") or 0),
            default=None,
        )
        if best:
            thumbnail = best.get("url", thumbnail)
    return thumbnail


def build_extract_options(
    *,
    cookiefile: Path | None = None,
    extract_flat: bool = False,
    playlist_end: int | None = None,
    ignore_config: bool = False,
    extractor_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "ignoreconfig": False,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": extract_flat,
    }
    if not extract_flat:
        options["format"] = "best/bestvideo+bestaudio"
    if cookiefile and cookiefile.is_file():
        options["cookiefile"] = str(cookiefile)
    if playlist_end is not None:
        options["playlistend"] = playlist_end
    if extractor_args:
        options["extractor_args"] = extractor_args
    return options


def build_download_base_options(
    *,
    output_dir: Path,
    cookiefile: Path | None = None,
    ignore_config: bool = False,
    extractor_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    options: dict[str, Any] = {
        "ignoreconfig": False,
        "outtmpl": str(output_dir / "media.%(ext)s"),
        "ffmpeg_location": get_ffmpeg_exe(),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [{"key": "FFmpegMetadata", "add_metadata": True}],
    }
    if cookiefile and cookiefile.is_file():
        options["cookiefile"] = str(cookiefile)
    if extractor_args:
        options["extractor_args"] = extractor_args
    return options
