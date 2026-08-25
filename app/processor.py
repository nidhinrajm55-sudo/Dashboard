from __future__ import annotations

import asyncio
import logging
import os
import socket
from datetime import datetime, timezone

from redis.asyncio import Redis

from .config import settings
from .models import WeatherReading
from .redis_streams import (
    DLQ_STREAM,
    PROCESSOR_GROUP,
    PROCESSED_STREAM,
    RAW_STREAM,
    StreamStore,
    decode_fields,
)

logger = logging.getLogger(__name__)


def parse_reading(fields: dict[str, str]) -> WeatherReading:
    return WeatherReading.model_validate(fields)


async def process_batch(store: StreamStore, batch: list[tuple[str, list[tuple[str, dict[bytes, bytes]]]]]) -> int:
    processed = 0
    for _, entries in batch:
        for message_id, encoded_fields in entries:
            message_id_text = message_id.decode() if isinstance(message_id, bytes) else message_id
            fields = decode_fields(encoded_fields)
            try:
                reading = parse_reading(fields)
                await store.publish(PROCESSED_STREAM, reading.model_dump(mode="json"))
                processed += 1
            except Exception as exc:  # invalid messages must never block the consumer
                try:
                    await store.publish(DLQ_STREAM, {
                        "original_id": message_id_text,
                        "payload": fields,
                        "error": str(exc),
                        "failed_at": datetime.now(timezone.utc).isoformat(),
                    })
                except Exception:
                    logger.exception("could not write message %s to DLQ; leaving it pending", message_id_text)
                    continue
                logger.exception("sent invalid message %s to DLQ", message_id_text)
            await store.ack(RAW_STREAM, PROCESSOR_GROUP, message_id_text)
    return processed


async def run() -> None:
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(message)s")
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    store = StreamStore(redis, settings.stream_maxlen)
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    await store.ensure_group(RAW_STREAM, PROCESSOR_GROUP)
    logger.info("processor %s listening on %s", consumer, RAW_STREAM)
    try:
        while True:
            batch = await store.read_group(RAW_STREAM, PROCESSOR_GROUP, consumer)
            if batch:
                await process_batch(store, batch)
    finally:
        await redis.aclose()


if __name__ == "__main__":
    asyncio.run(run())
