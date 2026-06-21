from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import CachedClient


class FootballData:
    WORLD_CUP = 2000

    def __init__(self, api_key: str, cache_dir: Path) -> None:
        self._client = CachedClient(
            base_url="https://api.football-data.org",
            headers={"X-Auth-Token": api_key},
            cache_dir=cache_dir,
            min_interval=6.0,
        )

    def competition(self, code: int | str = WORLD_CUP) -> dict[str, Any]:
        return self._client.get(f"/v4/competitions/{code}", ttl=86400)

    def equipo(self, team_id: int) -> dict[str, Any]:
        return self._client.get(f"/v4/teams/{team_id}", ttl=86400)

    def standings(self, code: int | str = WORLD_CUP, **params: Any) -> dict[str, Any]:
        return self._client.get(f"/v4/competitions/{code}/standings", params=params, ttl=3600)

    def matches(self, code: int | str = WORLD_CUP, **params: Any) -> dict[str, Any]:
        return self._client.get(f"/v4/competitions/{code}/matches", params=params, ttl=3600)

    def teams(self, code: int | str = WORLD_CUP, **params: Any) -> dict[str, Any]:
        return self._client.get(f"/v4/competitions/{code}/teams", params=params, ttl=86400)

    def close(self) -> None:
        self._client.close()
