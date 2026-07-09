# WeatherService — 수집 Business Logic: Adapter 호출(Retry) → Validation/Mapping → Repository 저장
import asyncio
from datetime import datetime, timezone

from pydantic import ValidationError

from common.core.exceptions import ExternalApiError
from common.core.logger import get_logger
from common.core.metrics import (
    LATEST_WEATHER_TIMESTAMP,
    WEATHER_FAILURE_TOTAL,
    WEATHER_SUCCESS_TOTAL,
    metrics,
)
from common.db.database import Database
from common.models.weather import WeatherRecord

from adapters.weather_adapter import WeatherAdapter
from config import WeatherSettings
from repositories.weather_repository import WeatherRepository

logger = get_logger("weather_service")


class WeatherService:
    def __init__(self, adapter: WeatherAdapter, database: Database, settings: WeatherSettings):
        self._adapter = adapter
        self._db = database
        self._settings = settings

    async def collect_all(self) -> int:
        """전체 구역 수집. 일부 구역 실패는 기록만 하고 나머지 구역은 계속 수집한다."""
        saved = 0
        for zone_id, (lat, lon) in self._settings.locations().items():
            try:
                record = await self._collect_zone(zone_id, lat, lon)
                saved += self._save(record)
            except (ExternalApiError, ValidationError) as exc:
                metrics.increment(WEATHER_FAILURE_TOTAL)
                logger.error(
                    f"weather collection failed for zone {zone_id}: {exc}",
                    extra={"event": "weather_failure", "detail": {"zone": zone_id}},
                )
        return saved

    async def _collect_zone(self, zone_id: str, lat: float, lon: float) -> WeatherRecord:
        raw = await self._fetch_with_retry(lat, lon)
        # Mapping + Validation (물리 범위 검증은 WeatherRecord가 수행)
        return WeatherRecord(
            zone_id=zone_id,
            observed_at=self._parse_time(raw["time"]),
            latitude=lat,
            longitude=lon,
            timezone_name=raw.get("timezone", "UTC"),
            temperature_c=raw.get("temperature_c"),
            humidity_pct=raw.get("humidity_pct"),
            rain_mm=raw.get("rain_mm"),
            precipitation_mm=raw.get("precipitation_mm"),
            wind_speed_kmh=raw.get("wind_speed_kmh"),
            cloud_cover_pct=raw.get("cloud_cover_pct"),
            weather_code=raw.get("weather_code"),
            visibility_m=raw.get("visibility_m"),
            source=self._adapter.provider,
        )

    async def _fetch_with_retry(self, lat: float, lon: float) -> dict:
        last_exc: ExternalApiError | None = None
        for attempt in range(1, self._settings.weather_retry_count + 1):
            try:
                return await self._adapter.fetch_current(lat, lon)
            except ExternalApiError as exc:
                last_exc = exc
                logger.warning(
                    f"weather request retry {attempt}/{self._settings.weather_retry_count}: {exc.message}",
                    extra={"event": "weather_retry", "count": attempt},
                )
                if attempt < self._settings.weather_retry_count:
                    await asyncio.sleep(self._settings.weather_retry_backoff_seconds * attempt)
        raise last_exc  # Retry 소진 — 호출부(collect_all)가 기록하고 다음 구역 진행

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)  # Open-Meteo는 timezone=UTC로 요청
        return parsed

    def _save(self, record: WeatherRecord) -> int:
        with self._db.session_scope() as session:
            inserted = WeatherRepository(session).upsert(record)
        metrics.increment(WEATHER_SUCCESS_TOTAL)
        metrics.observe(LATEST_WEATHER_TIMESTAMP, record.observed_at.timestamp())
        logger.info(
            "weather saved" if inserted else "weather updated (duplicate time)",
            extra={
                "event": "weather_saved",
                "detail": {
                    "zone": record.zone_id,
                    "observed_at": record.observed_at.isoformat(),
                    "inserted": inserted,
                },
            },
        )
        return 1 if inserted else 0
