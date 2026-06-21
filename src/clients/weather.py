from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import CachedClient


class Weather:
    def __init__(self, api_key: str, cache_dir: Path) -> None:
        self._key = api_key
        self._client = CachedClient(
            base_url="https://api.openweathermap.org",
            headers={},
            cache_dir=cache_dir,
            min_interval=1.0,
        )

    def forecast(self, lat: float, lon: float, ttl: float = 3600) -> dict[str, Any]:
        return self._client.get(
            "/data/2.5/forecast",
            params={"lat": lat, "lon": lon, "appid": self._key, "units": "metric"},
            ttl=ttl,
        )

    def close(self) -> None:
        self._client.close()
