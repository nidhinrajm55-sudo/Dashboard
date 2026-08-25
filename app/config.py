from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    latitude: float
    longitude: float


DEFAULT_LOCATIONS = (
    Location("seattle", "Seattle", 47.6062, -122.3321),
    Location("new-york", "New York", 40.7128, -74.0060),
    Location("london", "London", 51.5072, -0.1276),
)


@dataclass(frozen=True)
class Settings:
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    ingest_interval_seconds: int = int(os.getenv("INGEST_INTERVAL_SECONDS", "300"))
    stream_maxlen: int = int(os.getenv("STREAM_MAXLEN", "1000"))
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    @property
    def locations(self) -> tuple[Location, ...]:
        raw = os.getenv("LOCATIONS_JSON")
        if not raw:
            return DEFAULT_LOCATIONS
        try:
            values = json.loads(raw)
            return tuple(Location(**item) for item in values)
        except (json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
            raise ValueError("LOCATIONS_JSON must be a JSON array of location objects") from exc


settings = Settings()
