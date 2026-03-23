from __future__ import annotations

import asyncio
import json
import secrets
import sqlite3
from datetime import timedelta
from pathlib import Path

from models import SessionData, utcnow


class SessionStore:
    def __init__(self, db_path: Path, default_ttl_seconds: int) -> None:
        self.db_path = db_path
        self.default_ttl_seconds = default_ttl_seconds
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
                CREATE TABLE IF NOT EXISTS sessions (
                    job_id TEXT PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    provider TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    async def create_session(self, session: SessionData) -> SessionData:
        async with self._lock:
            await asyncio.to_thread(self._create_session_sync, session)
        return session

    def _create_session_sync(self, session: SessionData) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO sessions(job_id, user_id, provider, payload_json, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    session.job_id,
                    session.user_id,
                    session.provider.value,
                    json.dumps(session.to_dict(), ensure_ascii=False),
                    session.created_at.isoformat(),
                    session.expires_at.isoformat(),
                ),
            )
            conn.commit()

    async def get_session(self, job_id: str, *, user_id: int | None = None) -> SessionData | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_session_sync, job_id, user_id)

    def _get_session_sync(self, job_id: str, user_id: int | None) -> SessionData | None:
        now = utcnow().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload_json, user_id, expires_at FROM sessions WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            if user_id is not None and int(row["user_id"]) != user_id:
                return None
            if row["expires_at"] <= now:
                conn.execute("DELETE FROM sessions WHERE job_id = ?", (job_id,))
                conn.commit()
                return None
            return SessionData.from_dict(json.loads(row["payload_json"]))

    async def cleanup_expired(self) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._cleanup_expired_sync)

    def _cleanup_expired_sync(self) -> int:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (utcnow().isoformat(),))
            conn.commit()
            return int(cursor.rowcount)

    def build_session(self, *, user_id: int, media_info, source_url: str) -> SessionData:
        created_at = utcnow()
        expires_at = created_at + timedelta(seconds=self.default_ttl_seconds)
        return SessionData(
            job_id=self.generate_job_id(),
            user_id=user_id,
            provider=media_info.provider,
            source_url=source_url,
            media_info=media_info,
            created_at=created_at,
            expires_at=expires_at,
        )

    @staticmethod
    def generate_job_id() -> str:
        return secrets.token_urlsafe(8).replace("-", "").replace("_", "")[:11]
