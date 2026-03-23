from __future__ import annotations

from utils.files import calculate_segment_duration


def test_chunking_decision_reduces_large_file() -> None:
    duration = calculate_segment_duration(
        total_size_bytes=200 * 1024 * 1024,
        total_duration_seconds=1000,
        max_size_bytes=49 * 1024 * 1024,
    )
    assert 15 <= duration < 1000


def test_chunking_decision_keeps_small_file() -> None:
    duration = calculate_segment_duration(
        total_size_bytes=10 * 1024 * 1024,
        total_duration_seconds=300,
        max_size_bytes=49 * 1024 * 1024,
    )
    assert duration == 300
