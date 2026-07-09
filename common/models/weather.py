# Weather DTO — 외부 API 응답 검증(Validation) 및 조회 API 응답에 사용
from datetime import datetime

from pydantic import BaseModel, Field


class WeatherRecord(BaseModel):
    """검증된 날씨 1건. Adapter 원시 응답 → Service에서 이 모델로 매핑/검증한다."""

    zone_id: str = Field(..., min_length=1, max_length=32)
    observed_at: datetime
    data_type: str = Field(default="current", pattern="^(current|forecast)$")
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    timezone_name: str = "UTC"

    # 물리적으로 유효한 범위로 응답값 검증 (Null 허용 — 결측 Feature는 모델 단계에서 처리)
    temperature_c: float | None = Field(default=None, ge=-60, le=60)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    rain_mm: float | None = Field(default=None, ge=0)
    precipitation_mm: float | None = Field(default=None, ge=0)
    wind_speed_kmh: float | None = Field(default=None, ge=0)
    cloud_cover_pct: float | None = Field(default=None, ge=0, le=100)
    weather_code: int | None = Field(default=None, ge=0, le=99)
    visibility_m: float | None = Field(default=None, ge=0)

    source: str = "open-meteo"


class WeatherStatusResponse(BaseModel):
    """GET /weather/status — Dashboard용 수집 상태."""

    scheduler_running: bool
    interval_seconds: float
    zones: int
    total_records: int
    latest_observed_at: datetime | None = None
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    run_count: int
    failure_count: int
