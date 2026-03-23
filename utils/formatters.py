from __future__ import annotations

import html
from datetime import datetime


def escape_html(value: str | None) -> str:
    return html.escape(value or "")


def ellipsize(value: str | None, max_length: int) -> str:
    text = (value or "").strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 1]}…"


def format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_duration(seconds: int | None) -> str:
    if not seconds:
        return "Không rõ"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_views(value: int | None) -> str:
    if value is None:
        return "Không rõ"
    return f"{value:,}".replace(",", ".")


def format_date(value: str | None) -> str:
    if not value:
        return "Không rõ"
    raw = str(value)
    if len(raw) == 8 and raw.isdigit():
        return f"{raw[6:8]}/{raw[4:6]}/{raw[:4]}"
    try:
        return datetime.fromisoformat(raw).strftime("%d/%m/%Y")
    except ValueError:
        return raw


def build_part_caption(base_caption: str, index: int, total: int) -> str:
    if total <= 1:
        return base_caption
    return f"{base_caption}\nPhần {index}/{total}"
