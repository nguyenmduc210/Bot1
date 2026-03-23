from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx


class AsyncHTTPClient:
    def __init__(self, *, timeout_seconds: float, max_retries: int, backoff_seconds: float) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._client = httpx.AsyncClient(
            follow_redirects=True,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        )

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        response = await self.request("GET", url, params=params, headers=headers, timeout_seconds=timeout_seconds)
        return response.json()

    async def post_json(
        self,
        url: str,
        *,
        json_body: dict[str, Any],
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        response = await self.request(
            "POST",
            url,
            headers=headers,
            json_body=json_body,
            timeout_seconds=timeout_seconds,
        )
        return response.json()

    async def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
    ) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    timeout=timeout_seconds or self.timeout_seconds,
                )
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                if attempt == self.max_retries:
                    break
                await asyncio.sleep(self.backoff_seconds * attempt)
        raise last_error or RuntimeError("HTTP request failed")

    async def download_file(
        self,
        url: str,
        destination: Path,
        *,
        headers: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> int:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with self._client.stream(
                    "GET",
                    url,
                    headers=headers,
                    timeout=timeout_seconds or self.timeout_seconds,
                ) as response:
                    response.raise_for_status()
                    with destination.open("wb") as handle:
                        async for chunk in response.aiter_bytes(512 * 1024):
                            if chunk:
                                handle.write(chunk)
                return destination.stat().st_size
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                destination.unlink(missing_ok=True)
                if attempt == self.max_retries:
                    break
                await asyncio.sleep(self.backoff_seconds * attempt)
        raise last_error or RuntimeError("HTTP download failed")

    async def close(self) -> None:
        await self._client.aclose()
