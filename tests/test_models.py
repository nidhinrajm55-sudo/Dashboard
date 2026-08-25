from datetime import datetime

import pytest
from pydantic import ValidationError

from app.models import WeatherReading


def test_reading_normalises_naive_datetime_to_utc():
    reading = WeatherReading(
        location_id="x", location_name="Example", latitude=0, longitude=0,
        observed_at=datetime(2025, 1, 1, 12), temperature_c=20,
    )
    assert reading.observed_at.tzinfo is not None
    assert reading.observed_at.isoformat() == "2025-01-01T12:00:00+00:00"


def test_reading_rejects_invalid_coordinates():
    with pytest.raises(ValidationError):
        WeatherReading(location_id="x", location_name="Example", latitude=100, longitude=0,
                       observed_at="2025-01-01T00:00:00Z")
