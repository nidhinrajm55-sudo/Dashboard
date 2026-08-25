import httpx
import pytest

from app.config import Location
from app.ingest import fetch_weather


@pytest.mark.asyncio
async def test_fetch_weather_maps_open_meteo_current_payload():
    location = Location("test", "Test City", 10, 20)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["timezone"] == "UTC"
        return httpx.Response(200, json={"current": {
            "time": "2025-01-01T12:00",
            "temperature_2m": 21.4,
            "relative_humidity_2m": 55,
            "apparent_temperature": 20.9,
            "precipitation": 0,
            "weather_code": 1,
            "wind_speed_10m": 8.2,
        }})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        reading = await fetch_weather(client, location)

    assert reading["location_id"] == "test"
    assert reading["temperature_c"] == 21.4
    assert reading["observed_at"] == "2025-01-01T12:00:00+00:00"
