# Weather DI 조립 — Adapter/Store/Service/Scheduler 싱글턴 provider
from functools import lru_cache

from common.aws.client_factory import AwsClientFactory
from common.aws.s3_adapter import S3Adapter
from common.core.store import FileStore

from adapters.open_meteo_adapter import OpenMeteoAdapter
from adapters.weather_adapter import WeatherAdapter
from config import get_settings
from schedulers.weather_scheduler import WeatherScheduler
from services.weather_service import WeatherService


@lru_cache
def get_aws_client_factory() -> AwsClientFactory:
    settings = get_settings()
    return AwsClientFactory(settings.aws_region, settings.aws_endpoint_url)


@lru_cache
def get_s3_adapter() -> S3Adapter:
    settings = get_settings()
    return S3Adapter(get_aws_client_factory(), bucket=settings.s3_bucket, auto_create=settings.s3_auto_create_bucket)


@lru_cache
def get_file_store() -> FileStore:
    settings = get_settings()
    s3_adapter = get_s3_adapter() if settings.json_store_backend == "s3" else None
    return FileStore(settings.json_store_backend, settings.json_store_local_dir, s3_adapter)


@lru_cache
def get_weather_adapter() -> WeatherAdapter:
    # Provider 교체 지점 — 기상청/OpenWeather 등은 여기서 구현체만 바꾼다
    settings = get_settings()
    return OpenMeteoAdapter(settings.weather_api_url, settings.weather_timeout_seconds)


@lru_cache
def get_weather_service() -> WeatherService:
    return WeatherService(get_weather_adapter(), get_file_store(), get_settings())


@lru_cache
def get_weather_scheduler() -> WeatherScheduler:
    settings = get_settings()
    return WeatherScheduler(
        get_weather_service(),
        settings.weather_interval_seconds,
        align_offset_seconds=settings.weather_align_offset_seconds,
    )
