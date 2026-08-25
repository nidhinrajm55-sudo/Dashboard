from datetime import datetime, timezone

import fakeredis.aioredis
import pytest

from app.processor import process_batch
from app.redis_streams import DLQ_STREAM, PROCESSOR_GROUP, PROCESSED_STREAM, RAW_STREAM, StreamStore


def fields(**overrides):
    data = {
        "location_id": "seattle", "location_name": "Seattle", "latitude": "47.6", "longitude": "-122.3",
        "observed_at": datetime.now(timezone.utc).isoformat(), "temperature_c": "12.5",
        "humidity_percent": "80", "wind_speed_kmh": "7", "weather_code": "3",
    }
    data.update(overrides)
    return {key.encode(): value.encode() for key, value in data.items()}


@pytest.mark.asyncio
async def test_valid_message_is_processed_and_acked():
    redis = fakeredis.aioredis.FakeRedis()
    store = StreamStore(redis)
    await store.ensure_group(RAW_STREAM, PROCESSOR_GROUP)
    message_id = await redis.xadd(RAW_STREAM, fields())
    batch = [(RAW_STREAM, [(message_id, fields())])]
    assert await process_batch(store, batch) == 1
    processed = await store.latest(PROCESSED_STREAM)
    assert processed[0]["location_id"] == "seattle"
    assert await redis.xpending(RAW_STREAM, PROCESSOR_GROUP) == {"pending": 0, "min": None, "max": None, "consumers": []}


@pytest.mark.asyncio
async def test_invalid_message_goes_to_dlq_and_is_acked():
    redis = fakeredis.aioredis.FakeRedis()
    store = StreamStore(redis)
    await store.ensure_group(RAW_STREAM, PROCESSOR_GROUP)
    message_id = await redis.xadd(RAW_STREAM, fields(latitude="not-a-number"))
    batch = [(RAW_STREAM, [(message_id, fields(latitude="not-a-number"))])]
    assert await process_batch(store, batch) == 0
    dlq = await store.latest(DLQ_STREAM)
    assert dlq[0]["original_id"]
    assert "latitude" in dlq[0]["error"]
