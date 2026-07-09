# Open-Meteo 구현체 — https://open-meteo.com (API 키 불필요)
import time

import httpx

from common.core.exceptions import ExternalApiError
from common.core.logger import get_logger
from common.core.metrics import WEATHER_REQUEST_LATENCY_SECONDS, WEATHER_REQUEST_TOTAL, metrics

from adapters.weather_adapter import WeatherAdapter

logger = get_logger("open_meteo")

# Open-Meteo current 파라미터 → 중립 필드 매핑
_CURRENT_FIELDS = {
    "temperature_2m": "temperature_c",
    "relative_humidity_2m": "humidity_pct",
    "rain": "rain_mm",
    "precipitation": "precipitation_mm",
    "wind_speed_10m": "wind_speed_kmh",
    "cloud_cover": "cloud_cover_pct",
    "weather_code": "weather_code",
}


class OpenMeteoAdapter(WeatherAdapter):
    provider = "open-meteo"

    def __init__(self, base_url: str, timeout_seconds: float):
        self._base_url = base_url
        self._timeout = timeout_seconds

    async def fetch_current(self, latitude: float, longitude: float) -> dict:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(_CURRENT_FIELDS.keys()),
            "timezone": "UTC",
        }
        metrics.increment(WEATHER_REQUEST_TOTAL)
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info(
                    "weather request",
                    extra={"event": "weather_request", "detail": {"lat": latitude, "lon": longitude}},
                )
                response = await client.get(self._base_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise ExternalApiError(
                f"open-meteo request failed: {exc}",
                provider=self.provider,
                detail={"lat": latitude, "lon": longitude},
            ) from exc
        finally:
            metrics.observe(WEATHER_REQUEST_LATENCY_SECONDS, time.monotonic() - started)

        current = payload.get("current")
        if not isinstance(current, dict) or "time" not in current:
            # Missing/Invalid 응답 — Service 재시도 대상
            raise ExternalApiError(
                "open-meteo response missing 'current' block",
                provider=self.provider,
                detail={"keys": list(payload.keys())},
            )

        raw = {
            "time": current["time"],
            "timezone": payload.get("timezone", "UTC"),
            "visibility_m": None,  # Open-Meteo current 미제공 (hourly 전용) — 스키마 자리 유지
        }
        for api_field, neutral_field in _CURRENT_FIELDS.items():
            raw[neutral_field] = current.get(api_field)
        logger.info(
            "weather response",
            extra={"event": "weather_response", "detail": {"time": raw["time"]}},
        )
        return raw
