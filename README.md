# Weather Stream

A small, complete real-time weather pipeline. Open-Meteo supplies current observations, Redis Streams provides durable buffering and consumer-group delivery, a FastAPI processor validates and republishes readings, and a FastAPI SSE endpoint powers the static dashboard.

## Architecture

```text
Open-Meteo API -> ingest service -> weather:raw Redis Stream
                                      |
                          processor consumer group
                           /                     \
              weather:processed               weather:dlq
                     |
                FastAPI /api/events (SSE)
                     |
                static dashboard
```

### Services

- **Redis**: persistence-backed Redis 7 instance and the stream broker.
- **ingest**: polls Open-Meteo for each configured location every five minutes and writes to `weather:raw`.
- **processor**: consumes `weather:raw` using the `weather-processors` group, validates each message with Pydantic, publishes valid data to `weather:processed`, and sends malformed messages to `weather:dlq` before acknowledging the original.
- **api**: serves the dashboard and JSON/SSE endpoints.

## Run with Docker Compose

```bash
docker compose up --build
```

Open <http://localhost:8000>. The first reading arrives after the ingest service completes its first Open-Meteo request. To trigger a one-off fetch without waiting for the interval:

```bash
docker compose run --rm ingest python -m app.ingest --once
```

Check service health at <http://localhost:8000/api/health>.

## Run locally

Redis must be running on `localhost:6379` (for example, `docker compose up redis -d`). Then create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload       # terminal 1
python -m app.processor              # terminal 2
python -m app.ingest                 # terminal 3
```

For a single ingestion pass:

```bash
python -m app.ingest --once
```

## Configuration

Copy `.env.example` to `.env` or export environment variables in each process:

| Variable | Default | Description |
| --- | --- | --- |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `INGEST_INTERVAL_SECONDS` | `300` | Delay between ingestion batches |
| `STREAM_MAXLEN` | `1000` | Approximate max entries retained per stream |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `LOCATIONS_JSON` | Seattle, New York, London | JSON array of `{id,name,latitude,longitude}` |

## API

- `GET /api/health` — Redis-backed health check.
- `GET /api/locations` — configured locations.
- `GET /api/weather/latest` — newest processed reading for each location. Optional `location_id` filter.
- `GET /api/weather/history?location_id=seattle&limit=24` — newest readings for one location.
- `GET /api/events` — Server-Sent Events stream of newly processed readings. Browser reconnects resume through `Last-Event-ID`; CLI clients can pass `last_id` with a Redis Stream ID.

A processed event is JSON and includes `location_id`, coordinates, UTC observation/ingestion timestamps, temperature, apparent temperature, humidity, precipitation, wind speed, weather code, and source.

## Tests

Tests use `fakeredis`, so they do not require a running Redis server:

```bash
pytest -q
```

## Operational notes

- Redis AOF persistence is enabled in Compose so queued readings survive a Redis container restart.
- The processor acknowledges every raw message after either successful processing or DLQ publication, preventing poison messages from blocking the consumer group.
- Stream entries are capped approximately with `MAXLEN` to keep the demo bounded. Increase `STREAM_MAXLEN` for longer history.
- Open-Meteo is free for non-commercial use and does not require an API key. Network failures are logged per location; the next interval retries them.
