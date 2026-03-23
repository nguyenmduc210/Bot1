from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import time
from pathlib import Path


def sanitize_filename(value: str, default: str = "media") -> str:
    cleaned = re.sub(r"[<>:\"/\\\\|?*\x00-\x1f]", "_", value).strip(" .")
    return cleaned[:120] or default


def tighten_permissions(path: Path) -> None:
    try:
        if os.name == "nt":
            os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        else:
            os.chmod(path, 0o600)
    except OSError:
        return


def validate_output_file(path: Path, allowed_extensions: tuple[str, ...] = ()) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Không tìm thấy file đầu ra: {path}")
    if path.stat().st_size <= 0:
        raise ValueError(f"File đầu ra rỗng: {path}")
    if allowed_extensions and path.suffix.lower() not in allowed_extensions:
        raise ValueError(f"File đầu ra sai định dạng: {path.suffix}")


def calculate_segment_duration(
    total_size_bytes: int,
    total_duration_seconds: int | None,
    max_size_bytes: int,
    *,
    safety_ratio: float = 0.92,
    min_seconds: int = 15,
    max_seconds: int = 1800,
) -> int:
    if total_duration_seconds is None or total_duration_seconds <= 0:
        return min_seconds
    if total_size_bytes <= max_size_bytes:
        return total_duration_seconds
    estimate = int(total_duration_seconds * (max_size_bytes / total_size_bytes) * safety_ratio)
    return max(min_seconds, min(max_seconds, estimate))


def probe_duration_seconds(ffmpeg_path: str, input_file: Path) -> int | None:
    result = subprocess.run(
        [ffmpeg_path, "-i", str(input_file)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stderr or result.stdout
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", output)
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return int(hours * 3600 + minutes * 60 + seconds)


def split_media_file(
    input_file: Path,
    output_dir: Path,
    *,
    max_size_bytes: int,
    is_video: bool,
    ffmpeg_path: str,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    total_duration = probe_duration_seconds(ffmpeg_path, input_file)
    segment_seconds = calculate_segment_duration(
        input_file.stat().st_size,
        total_duration,
        max_size_bytes,
        max_seconds=180 if is_video else 600,
    )
    extension = input_file.suffix or (".mp4" if is_video else ".mp3")

    for _ in range(4):
        for existing in output_dir.glob(f"part_*{extension}"):
            existing.unlink(missing_ok=True)

        output_pattern = output_dir / f"part_%03d{extension}"
        command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_file),
            "-c",
            "copy",
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            str(output_pattern),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        parts = sorted(output_dir.glob(f"part_*{extension}"))
        if result.returncode == 0 and parts and all(part.stat().st_size <= max_size_bytes for part in parts):
            return parts
        if segment_seconds <= 15:
            break
        segment_seconds = max(15, segment_seconds // 2)

    if is_video:
        fallback_dir = output_dir / "reencoded"
        fallback_dir.mkdir(parents=True, exist_ok=True)
        output_pattern = fallback_dir / "part_%03d.mp4"
        command = [
            ffmpeg_path,
            "-y",
            "-i",
            str(input_file),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "segment",
            "-segment_time",
            str(max(15, segment_seconds)),
            "-reset_timestamps",
            "1",
            str(output_pattern),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        parts = sorted(fallback_dir.glob("part_*.mp4"))
        if result.returncode == 0 and parts and all(part.stat().st_size <= max_size_bytes for part in parts):
            return parts

    raise RuntimeError("Không thể chia nhỏ file để phù hợp giới hạn Telegram.")


def extract_audio_to_mp3(input_file: Path, output_file: Path, *, ffmpeg_path: str) -> Path:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.unlink(missing_ok=True)
    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(input_file),
        "-map",
        "0:a:0",
        "-vn",
        "-c:a",
        "libmp3lame",
        "-b:a",
        "320k",
        str(output_file),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        error_output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(error_output or "ffmpeg failed to extract audio")
    validate_output_file(output_file, (".mp3",))
    input_file.unlink(missing_ok=True)
    return output_file


def remove_tree(path: Path, *, attempts: int = 5, delay_seconds: float = 0.2) -> None:
    for attempt in range(1, attempts + 1):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except PermissionError:
            for target in [path, *path.rglob("*")]:
                try:
                    os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
                except OSError:
                    continue
            time.sleep(delay_seconds * attempt)
    shutil.rmtree(path, ignore_errors=True)
