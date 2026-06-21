from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx


class CachedClient:
    def __init__(
        self,
        base_url: str,
        headers: dict[str, str],
        cache_dir: Path,
        min_interval: float = 1.0,
        max_retries: int = 3,
        timeout: float = 20.0,
    ) -> None:
        self._client = httpx.Client(base_url=base_url, headers=headers, timeout=timeout)
        self._cache_dir = cache_dir
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._last_request = 0.0
        cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_key(self, path: str, params: dict[str, Any]) -> Path:
        raw = path + json.dumps(params, sort_keys=True)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return self._cache_dir / f"{digest}.json"

    def _read_cache(self, key: Path, ttl: float) -> Any | None:
        if not key.exists():
            return None
        if ttl >= 0 and time.time() - key.stat().st_mtime > ttl:
            return None
        return json.loads(key.read_text(encoding="utf-8"))

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_request = time.time()

    def get(self, path: str, params: dict[str, Any] | None = None, ttl: float = 86400) -> Any:
        params = params or {}
        key = self._cache_key(path, params)
        cached = self._read_cache(key, ttl)
        if cached is not None:
            return cached
        last_exc: Exception | None = None
        for attempt in range(self._max_retries):
            self._throttle()
            try:
                resp = self._client.get(path, params=params)
                resp.raise_for_status()
                data = resp.json()
                key.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                return data
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                if exc.response.status_code == 429 and attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise
        raise RuntimeError(f"Fallo tras {self._max_retries} intentos en {path}: {last_exc}")

    def close(self) -> None:
        self._client.close()
