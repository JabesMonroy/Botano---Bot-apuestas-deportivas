from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import CachedClient


class ApiFootball:
    def __init__(self, api_key: str, host: str, cache_dir: Path) -> None:
        self._client = CachedClient(
            base_url=f"https://{host}",
            headers={"x-apisports-key": api_key},
            cache_dir=cache_dir,
            min_interval=1.0,
        )

    def status(self) -> dict[str, Any]:
        return self._client.get("/status", ttl=0)

    def fixtures(self, **params: Any) -> dict[str, Any]:
        return self._client.get("/fixtures", params=params)

    def head_to_head(self, h2h: str, **params: Any) -> dict[str, Any]:
        return self._client.get("/fixtures/headtohead", params={"h2h": h2h, **params})

    def fixture_statistics(self, fixture: int) -> dict[str, Any]:
        return self._client.get("/fixtures/statistics", params={"fixture": fixture})

    def lineups(self, fixture: int) -> dict[str, Any]:
        return self._client.get("/fixtures/lineups", params={"fixture": fixture})

    def injuries(self, **params: Any) -> dict[str, Any]:
        return self._client.get("/injuries", params=params)

    def close(self) -> None:
        self._client.close()
