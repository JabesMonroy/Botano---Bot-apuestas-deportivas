from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Config:
    api_football_key: str
    api_football_host: str
    odds_api_key: str
    openweather_key: str
    football_data_key: str
    data_dir: Path
    db_path: Path
    cache_dir: Path


def load_config() -> Config:
    data_dir = ROOT / "data"
    return Config(
        api_football_key=os.getenv("API_FOOTBALL_KEY", ""),
        api_football_host=os.getenv("API_FOOTBALL_HOST", "v3.football.api-sports.io"),
        odds_api_key=os.getenv("ODDS_API_KEY", ""),
        openweather_key=os.getenv("OPENWEATHER_KEY", ""),
        football_data_key=os.getenv("FOOTBALL_DATA_KEY", ""),
        data_dir=data_dir,
        db_path=data_dir / "bot.db",
        cache_dir=data_dir / "cache",
    )
