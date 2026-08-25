from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone

import httpx
from redis.asyncio import Redis

from .config import Location, settings
from .redis_streams import RAW_STREAM, StreamStore

logger = logging.getLogger(__name__)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
CURRENT_FIELDS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,"
    "weather_code,wind_speed_10m"
)


async def fetch_weather(client: httpx.AsyncClient, location: Location) -> dict:
    response = await client.get(
        OPEN_METEO_URL,
        params={
            "latitude": location.latitude,
            "longitude": location.longitude,
            "current": CURRENT_FIELDS,
            "timezone": "UTC",
        },
    )
    response.raise_for_status()
    current = response.json().get("current")
    if not isinstance(current, dict) or not current.get("time"):
        raise ValueError(f"Open-Meteo returned no current weather for {location.id}")
    observed_at = datetime.fromisoformat(current["time"].replace("Z", "+00:00"))
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=timezone.utc)
    else:
        observed_at = observed_at.astimezone(timezone.utc)
    return {
        "location_id": location.id,
        "location_name": location.name,
        "latitude": location.latitude,
        "longitude": location.longitude,
        "observed_at": observed_at.isoformat(),
        "ingested_at": datetime.now(timezone.utc).isoformat(),
        "temperature_c": current.get("temperature_2m"),
        "apparent_temperature_c": current.get("apparent_temperature"),
        "humidity_percent": current.get("relative_humidity_2m"),
        "precipitation_mm": current.get("precipitation"),
        "wind_speed_kmh": current.get("wind_speed_10m"),
        "weather_code": current.get("weather_code"),
        "source": "open-meteo",
    }


async def ingest_once(store: StreamStore, locations: tuple[Location, ...] = settings.locations) -> int:
    successes = 0
    async with httpx.AsyncClient(timeout=20) as client:
        for location in locations:
            try:
                reading = await fetch_weather(client, location)
                message_id = await store.publish(RAW_STREAM, reading)
                successes += 1
                logger.info("published %s weather reading as %s", location.id, message_id)
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("failed to ingest %s: %s", location.id, exc)
    return successes


async def run() -> None:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    store = StreamStore(redis, settings.stream_maxlen)
    try:
        while True:
            await ingest_once(store)
            await asyncio.sleep(settings.ingest_interval_seconds)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest current weather into a Redis Stream")
    parser.add_argument("--once", action="store_true", help="fetch one batch and exit")
    args = parser.parse_args()
    if args.once:
        async def once() -> None:
            redis = Redis.from_url(settings.redis_url, decode_responses=False)
            try:
                await ingest_once(StreamStore(redis, settings.stream_maxlen))
            finally:
                await redis.aclose()
        asyncio.run(once())
    else:
        asyncio.run(run())
