from __future__ import annotations

import sys

from src.clients.api_football import ApiFootball
from src.clients.odds_api import OddsApi
from src.clients.weather import Weather
from src.config import load_config


def main() -> int:
    cfg = load_config()
    ok = True

    if cfg.api_football_key:
        client = ApiFootball(cfg.api_football_key, cfg.api_football_host, cfg.cache_dir / "api_football")
        try:
            data = client.status()
            req = data.get("response", {}).get("requests", {})
            print(f"[API-Football] OK - requests: {req.get('current')}/{req.get('limit_day')}")
        except Exception as exc:
            ok = False
            print(f"[API-Football] ERROR: {exc}")
        finally:
            client.close()
    else:
        print("[API-Football] sin key (API_FOOTBALL_KEY)")

    if cfg.odds_api_key:
        client = OddsApi(cfg.odds_api_key, cfg.cache_dir / "odds_api")
        try:
            sports = client.sports()
            print(f"[The Odds API] OK - {len(sports)} deportes disponibles")
        except Exception as exc:
            ok = False
            print(f"[The Odds API] ERROR: {exc}")
        finally:
            client.close()
    else:
        print("[The Odds API] sin key (ODDS_API_KEY)")

    if cfg.openweather_key:
        client = Weather(cfg.openweather_key, cfg.cache_dir / "weather")
        try:
            client.forecast(40.7128, -74.0060)
            print("[OpenWeather] OK")
        except Exception as exc:
            ok = False
            print(f"[OpenWeather] ERROR: {exc}")
        finally:
            client.close()
    else:
        print("[OpenWeather] sin key (OPENWEATHER_KEY)")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
