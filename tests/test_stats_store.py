from __future__ import annotations

import asyncio

from services.stats_store import StatsStore


def test_stats_update_logic(tmp_path) -> None:
    store = StatsStore(tmp_path / "state.sqlite3")
    asyncio.run(store.record_request(100))
    asyncio.run(store.record_request(200))
    asyncio.run(store.record_item_processed(user_id=100, success=True, bytes_sent=1024, item_count=1))
    asyncio.run(store.record_item_processed(user_id=200, success=False, item_count=2))
    snapshot = asyncio.run(store.get_snapshot())
    assert snapshot.request_count == 2
    assert snapshot.item_processed_count == 3
    assert snapshot.success_count == 1
    assert snapshot.failure_count == 2
    assert snapshot.total_bytes == 1024
    assert snapshot.unique_users == 2
