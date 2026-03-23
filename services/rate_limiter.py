from __future__ import annotations

import asyncio
import time


class RateLimiter:
    def __init__(self, cooldown_seconds: float) -> None:
        self.cooldown_seconds = cooldown_seconds
        self._lock = asyncio.Lock()
        self._last_request: dict[int, float] = {}

    async def check_and_update(self, user_id: int) -> float:
        now = time.monotonic()
        async with self._lock:
            last = self._last_request.get(user_id, 0.0)
            remaining = self.cooldown_seconds - (now - last)
            if remaining > 0:
                return remaining
            self._last_request[user_id] = now
            return 0.0
