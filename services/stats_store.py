from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from models import StatsSnapshot, utcnow


class StatsStore:
    COUNTERS = (
        "request_count",
        "item_processed_count",
        "success_count",
        "failure_count",
        "total_bytes",
    )

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = asyncio.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stats_counters (
                    key TEXT PRIMARY KEY,
                    value INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS seen_users (
                    user_id INTEGER PRIMARY KEY,
                    first_seen_at TEXT NOT NULL
                )
                """
            )
            for counter in self.COUNTERS:
                conn.execute(
                    "INSERT OR IGNORE INTO stats_counters(key, value) VALUES(?, 0)",
                    (counter,),
                )
            conn.commit()

    async def mark_user_seen(self, user_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._mark_user_seen_sync, user_id)

    def _mark_user_seen_sync(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_users(user_id, first_seen_at) VALUES(?, ?)",
                (user_id, utcnow().isoformat()),
            )
            conn.commit()

    async def record_request(self, user_id: int) -> None:
        async with self._lock:
            await asyncio.to_thread(self._record_request_sync, user_id)

    def _record_request_sync(self, user_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_users(user_id, first_seen_at) VALUES(?, ?)",
                (user_id, utcnow().isoformat()),
            )
            conn.execute(
                "UPDATE stats_counters SET value = value + 1 WHERE key = 'request_count'"
            )
            conn.commit()

    async def record_item_processed(
        self,
        *,
        user_id: int,
        success: bool,
        bytes_sent: int = 0,
        item_count: int = 1,
    ) -> None:
        async with self._lock:
            await asyncio.to_thread(
                self._record_item_processed_sync,
                user_id,
                success,
                bytes_sent,
                item_count,
            )

    def _record_item_processed_sync(self, user_id: int, success: bool, bytes_sent: int, item_count: int) -> None:
        counter_key = "success_count" if success else "failure_count"
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO seen_users(user_id, first_seen_at) VALUES(?, ?)",
                (user_id, utcnow().isoformat()),
            )
            conn.execute(
                "UPDATE stats_counters SET value = value + ? WHERE key = 'item_processed_count'",
                (item_count,),
            )
            conn.execute(
                "UPDATE stats_counters SET value = value + ? WHERE key = ?",
                (item_count, counter_key),
            )
            if bytes_sent > 0:
                conn.execute(
                    "UPDATE stats_counters SET value = value + ? WHERE key = 'total_bytes'",
                    (bytes_sent,),
                )
            conn.commit()

    async def get_snapshot(self) -> StatsSnapshot:
        async with self._lock:
            return await asyncio.to_thread(self._get_snapshot_sync)

    def _get_snapshot_sync(self) -> StatsSnapshot:
        with self._connect() as conn:
            counter_rows = conn.execute("SELECT key, value FROM stats_counters").fetchall()
            counters = {row["key"]: int(row["value"]) for row in counter_rows}
            unique_users = conn.execute("SELECT COUNT(*) FROM seen_users").fetchone()[0]
        return StatsSnapshot(
            request_count=counters.get("request_count", 0),
            item_processed_count=counters.get("item_processed_count", 0),
            success_count=counters.get("success_count", 0),
            failure_count=counters.get("failure_count", 0),
            total_bytes=counters.get("total_bytes", 0),
            unique_users=int(unique_users),
        )
