# Weather Collector 설정 — NYC 단일 지점 예보 수집. API URL·주기·재시도 전부 환경변수.
from functools import lru_cache

from common.core.constants import WEATHER_FORECAST_CSV_KEY
from common.core.settings import BaseAppSettings


class WeatherSettings(BaseAppSettings):
    service_name: str = "weather-cron"

    # --- 외부 API (Open-Meteo, API 키 불필요) ---
    weather_api_url: str = "https://api.open-meteo.com/v1/forecast"
    weather_timeout_seconds: float = 10.0
    weather_retry_count: int = 3
    weather_retry_backoff_seconds: float = 2.0

    # --- 예보 수집 범위 ---
    # 한 번 호출로 받아오는 시간 단위 예보 길이. predict가 시간대별(30분 단위 강수 변화
    # 포함) 최악 시나리오를 골라 쓸 수 있도록 넉넉히 잡는다.
    weather_forecast_hours: int = 30

    # --- Scheduler: UTC 자정(00:00) 기준 4시간마다 정렬 실행 ---
    weather_interval_seconds: float = 4 * 3600
    weather_align_offset_seconds: float = 0.0

    # --- 저장 위치 (FileStore 키) — predict가 같은 키로 읽는다 ---
    weather_csv_key: str = WEATHER_FORECAST_CSV_KEY

    # --- S3 (LocalStack/moto 전용 — 운영은 IaC가 버킷 소유) ---
    s3_auto_create_bucket: bool = False


@lru_cache
def get_settings() -> WeatherSettings:
    return WeatherSettings()
