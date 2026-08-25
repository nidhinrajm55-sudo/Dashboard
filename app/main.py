from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from .config import settings
from .redis_streams import PROCESSED_STREAM, StreamStore, _decode

logger = logging.getLogger(__name__)


def _normalise(value: str) -> object:
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def serialise(fields: dict[str, str]) -> dict:
    return {key: _normalise(value) for key, value in fields.items()}


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    app.state.redis = redis
    app.state.store = StreamStore(redis, settings.stream_maxlen)
    try:
        yield
    finally:
        await redis.aclose()


app = FastAPI(title="Real-time Weather Pipeline", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


def get_store(request: Request) -> StreamStore:
    return request.app.state.store


@app.get("/api/health")
async def health(request: Request) -> dict:
    try:
        await request.app.state.redis.ping()
        return {"status": "ok", "redis": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"redis unavailable: {exc}") from exc


@app.get("/api/locations")
async def locations() -> list[dict]:
    return [location.__dict__ for location in settings.locations]


@app.get("/api/weather/latest")
async def latest(request: Request, location_id: str | None = None) -> list[dict]:
    entries = await get_store(request).latest(PROCESSED_STREAM, count=500)
    seen: set[str] = set()
    result = []
    for entry in entries:
        item = serialise(entry)
        current_location = item.get("location_id")
        if location_id and current_location != location_id:
            continue
        if current_location in seen:
            continue
        seen.add(str(current_location))
        result.append(item)
    return result


@app.get("/api/weather/history")
async def history(request: Request, location_id: str, limit: int = 24) -> list[dict]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 500")
    entries = await get_store(request).latest(PROCESSED_STREAM, count=500)
    result = []
    for entry in entries:
        item = serialise(entry)
        if item.get("location_id") == location_id:
            result.append(item)
    return result[:limit]


async def event_stream(request: Request, cursor: str) -> AsyncIterator[str]:
    redis: Redis = request.app.state.redis
    while True:
        if await request.is_disconnected():
            return
        try:
            response = await asyncio.wait_for(
                redis.xread({PROCESSED_STREAM: cursor}, count=25, block=15000), timeout=20
            )
        except asyncio.TimeoutError:
            yield ": heartbeat\n\n"
            continue
        except Exception:
            logger.exception("SSE Redis read failed")
            yield "event: error\ndata: {\"message\":\"stream unavailable\"}\n\n"
            await asyncio.sleep(2)
            continue
        if not response:
            yield ": heartbeat\n\n"
            continue
        for _, entries in response:
            for message_id, fields in entries:
                cursor = _decode(message_id)
                payload = serialise({_decode(k): _decode(v) for k, v in fields.items()})
                yield f"id: {cursor}\nevent: weather\nretry: 3000\ndata: {json.dumps(payload)}\n\n"


@app.get("/api/events")
async def events(
    request: Request,
    last_id: str | None = None,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse:
    # EventSource sends Last-Event-ID automatically after reconnecting. Keep the
    # query parameter as a convenient override for curl and other clients.
    cursor = last_id or last_event_id or "$"
    return StreamingResponse(
        event_stream(request, cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Content-Type": "text/event-stream; charset=utf-8",
        },
    )


app.mount("/", StaticFiles(directory="static", html=True), name="static")
