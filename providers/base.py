from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from config import Settings
from models import DownloadPlan, MediaInfo, SessionData
from services.cookie_store import CookieStore
from services.http_client import AsyncHTTPClient


class BaseProvider(ABC):
    def __init__(self, settings: Settings, http_client: AsyncHTTPClient, cookie_store: CookieStore) -> None:
        self.settings = settings
        self.http_client = http_client
        self.cookie_store = cookie_store

    @property
    @abstractmethod
    def key(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def supports(self, url: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    async def extract_info(self, url: str, *, user_id: int) -> MediaInfo:
        raise NotImplementedError

    @abstractmethod
    def build_download_options(
        self,
        *,
        action: str,
        session: SessionData,
        output_dir: Path,
        item_index: int | None = None,
    ) -> DownloadPlan:
        raise NotImplementedError
