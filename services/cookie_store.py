from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from pathlib import Path

from models import CookieMetadata, utcnow
from utils.files import tighten_permissions


class CookieStore:
    def __init__(self, db_path: Path, cookies_dir: Path) -> None:
        self.db_path = db_path
        self.cookies_dir = cookies_dir
        self._lock = asyncio.Lock()
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, check_same_thread=False)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cookies (
                    user_id INTEGER PRIMARY KEY,
                    path TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    line_count INTEGER NOT NULL
                )
                """
            )
            conn.commit()

    def cookie_path(self, user_id: int) -> Path:
        return self.cookies_dir / f"{user_id}.txt"

    async def has_cookie(self, user_id: int) -> bool:
        return self.cookie_path(user_id).is_file()

    async def get_cookie_path(self, user_id: int) -> Path | None:
        path = self.cookie_path(user_id)
        return path if path.is_file() else None

    async def get_cookie_metadata(self, user_id: int) -> CookieMetadata | None:
        async with self._lock:
            return await asyncio.to_thread(self._get_cookie_metadata_sync, user_id)

    def _get_cookie_metadata_sync(self, user_id: int) -> CookieMetadata | None:
        path = self.cookie_path(user_id)
        if not path.is_file():
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT updated_at, line_count FROM cookies WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return None
        return CookieMetadata(
            user_id=user_id,
            path=path,
            updated_at=datetime.fromisoformat(row["updated_at"]),
            line_count=int(row["line_count"]),
        )

    async def save_cookie_file(self, user_id: int, source_path: Path) -> CookieMetadata:
        async with self._lock:
            return await asyncio.to_thread(self._save_cookie_file_sync, user_id, source_path)

    def _save_cookie_file_sync(self, user_id: int, source_path: Path) -> CookieMetadata:
        raw_text = source_path.read_text(encoding="utf-8", errors="replace")
        is_valid, reason, line_count = validate_cookies_txt(raw_text)
        if not is_valid:
            raise ValueError(reason)
        target_path = self.cookie_path(user_id)
        target_path.write_text(raw_text, encoding="utf-8")
        tighten_permissions(target_path)
        updated_at = utcnow()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO cookies(user_id, path, updated_at, line_count)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    path = excluded.path,
                    updated_at = excluded.updated_at,
                    line_count = excluded.line_count
                """,
                (user_id, str(target_path), updated_at.isoformat(), line_count),
            )
            conn.commit()
        return CookieMetadata(
            user_id=user_id,
            path=target_path,
            updated_at=updated_at,
            line_count=line_count,
        )

    async def delete_cookie(self, user_id: int) -> bool:
        async with self._lock:
            return await asyncio.to_thread(self._delete_cookie_sync, user_id)

    def _delete_cookie_sync(self, user_id: int) -> bool:
        target = self.cookie_path(user_id)
        removed = False
        if target.exists():
            target.unlink(missing_ok=True)
            removed = True
        with self._connect() as conn:
            conn.execute("DELETE FROM cookies WHERE user_id = ?", (user_id,))
            conn.commit()
        return removed

    async def cleanup_invalid_and_old(self, *, max_age_days: int | None = None) -> int:
        async with self._lock:
            return await asyncio.to_thread(self._cleanup_invalid_and_old_sync, max_age_days)

    def _cleanup_invalid_and_old_sync(self, max_age_days: int | None) -> int:
        deleted = 0
        now = utcnow()
        with self._connect() as conn:
            rows = conn.execute("SELECT user_id, path, updated_at FROM cookies").fetchall()
            for row in rows:
                path = Path(row["path"])
                should_delete = not path.exists()
                if not should_delete and max_age_days is not None:
                    age_days = (now - datetime.fromisoformat(row["updated_at"])).days
                    should_delete = age_days > max_age_days
                if not should_delete and path.exists():
                    valid, _, _ = validate_cookies_txt(path.read_text(encoding="utf-8", errors="replace"))
                    should_delete = not valid
                if should_delete:
                    path.unlink(missing_ok=True)
                    conn.execute("DELETE FROM cookies WHERE user_id = ?", (row["user_id"],))
                    deleted += 1
            conn.commit()
        return deleted


def validate_cookies_txt(raw_text: str) -> tuple[bool, str, int]:
    lines = raw_text.splitlines()
    header_present = any(
        line.strip().startswith("# Netscape HTTP Cookie File")
        or line.strip().startswith("# HTTP Cookie File")
        for line in lines[:5]
    )
    cookie_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        parts = stripped.split("\t")
        if len(parts) < 7:
            return False, "File không đúng định dạng Netscape cookies.txt.", 0
        cookie_lines.append(parts)
    if not cookie_lines:
        return False, "File cookies.txt không chứa cookie hợp lệ.", 0
    if not header_present:
        first = cookie_lines[0]
        if len(first) < 7:
            return False, "Thiếu header Netscape hoặc dữ liệu cookie không hợp lệ.", 0
    return True, "ok", len(cookie_lines)
