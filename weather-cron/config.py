# Weather Collector 설정 — API URL·좌표·주기·재시도 전부 환경변수 (매직넘버 금지)
from functools import lru_cache

from common.core.constants import ZONE_COORDINATES
from common.core.settings import BaseAppSettings


class WeatherSettings(BaseAppSettings):
    service_name: str = "weather-cron"

    # --- 외부 API (Open-Meteo, API 키 불필요) ---
    weather_api_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 10.0
    weather_retry_count: int = 3
    weather_retry_backoff_seconds: float = 2.0

    # --- 수집 대상 좌표 ---
    # 형식: "zone:lat:lon,zone:lat:lon". 미지정 시 공통 ZONE_COORDINATES(서울 9개 구역) 사용.
    weather_locations: str = ""

    # --- Scheduler ---
    weather_interval_seconds: float = 600.0  # 10분 (5/10/30분 등 환경변수로 조정)

    # --- 조회 API ---
    weather_history_default_hours: int = 24
    weather_history_max_limit: int = 500

    def locations(self) -> dict[str, tuple[float, float]]:
        if not self.weather_locations.strip():
            return dict(ZONE_COORDINATES)
        result: dict[str, tuple[float, float]] = {}
        for item in self.weather_locations.split(","):
            zone, lat, lon = item.strip().split(":")
            result[zone] = (float(lat), float(lon))
        return result


@lru_cache
def get_settings() -> WeatherSettings:
    return WeatherSettings()
