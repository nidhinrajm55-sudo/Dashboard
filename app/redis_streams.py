from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import ResponseError

logger = logging.getLogger(__name__)

RAW_STREAM = "weather:raw"
PROCESSED_STREAM = "weather:processed"
DLQ_STREAM = "weather:dlq"
PROCESSOR_GROUP = "weather-processors"


class StreamStore:
    def __init__(self, redis: Redis, maxlen: int = 1000) -> None:
        self.redis = redis
        self.maxlen = maxlen

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self.redis.xgroup_create(stream, group, id="0", mkstream=True)
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def publish(self, stream: str, payload: Mapping[str, Any]) -> str:
        encoded = {key: json.dumps(value) if isinstance(value, (dict, list)) else str(value)
                   for key, value in payload.items()}
        return await self.redis.xadd(stream, encoded, maxlen=self.maxlen, approximate=True)

    async def read_group(self, stream: str, group: str, consumer: str, count: int = 10,
                         block_ms: int = 5000) -> list[tuple[str, list[tuple[str, dict[bytes, bytes]]]]]:
        return await self.redis.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)

    async def ack(self, stream: str, group: str, message_id: str) -> int:
        return await self.redis.xack(stream, group, message_id)

    async def latest(self, stream: str, count: int = 100) -> list[dict[str, str]]:
        entries = await self.redis.xrevrange(stream, count=count)
        return [{_decode(k): _decode(v) for k, v in fields.items()} | {"id": _decode(entry_id)}
                for entry_id, fields in entries]


def _decode(value: bytes | str) -> str:
    return value.decode() if isinstance(value, bytes) else value


def decode_fields(fields: Mapping[bytes | str, bytes | str]) -> dict[str, str]:
    return {_decode(k): _decode(v) for k, v in fields.items()}
