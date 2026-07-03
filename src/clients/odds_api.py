from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import CachedClient


class OddsApi:
    def __init__(self, api_key: str, cache_dir: Path) -> None:
        self._key = api_key
        self._client = CachedClient(
            base_url="https://api.the-odds-api.com",
            headers={},
            cache_dir=cache_dir,
            min_interval=1.0,
        )

    def sports(self) -> list[dict[str, Any]]:
        return self._client.get("/v4/sports", params={"apiKey": self._key}, ttl=0)

    def odds(
        self,
        sport: str,
        regions: str = "eu",
        markets: str = "h2h",
        bookmakers: str = "pinnacle",
        ttl: float = 300,
    ) -> list[dict[str, Any]]:
        params = {
            "apiKey": self._key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
        }
        if bookmakers:
            params["bookmakers"] = bookmakers
        return self._client.get(f"/v4/sports/{sport}/odds", params=params, ttl=ttl)

    def event_odds(
        self,
        sport: str,
        event_id: str,
        markets: str,
        bookmakers: str = "pinnacle",
        ttl: float = 3600,
    ) -> dict[str, Any]:
        params = {
            "apiKey": self._key,
            "markets": markets,
            "oddsFormat": "decimal",
        }
        if bookmakers:
            params["bookmakers"] = bookmakers
        return self._client.get(f"/v4/sports/{sport}/events/{event_id}/odds", params=params, ttl=ttl)

    def close(self) -> None:
        self._client.close()
