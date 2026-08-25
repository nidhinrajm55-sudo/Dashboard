from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WeatherReading(BaseModel):
    model_config = ConfigDict(extra="ignore")

    location_id: str = Field(min_length=1)
    location_name: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    observed_at: datetime
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    temperature_c: float | None = None
    apparent_temperature_c: float | None = None
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    precipitation_mm: float | None = Field(default=None, ge=0)
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    weather_code: int | None = None
    source: str = "open-meteo"

    @field_validator("observed_at", "ingested_at")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
