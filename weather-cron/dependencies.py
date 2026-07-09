# Weather DI 조립 — Adapter/Service/Scheduler 싱글턴 provider
from functools import lru_cache
from typing import Iterator

from sqlalchemy.orm import Session

from common.db.database import Database

from adapters.open_meteo_adapter import OpenMeteoAdapter
from adapters.weather_adapter import WeatherAdapter
from config import get_settings
from schedulers.weather_scheduler import WeatherScheduler
from services.weather_service import WeatherService


@lru_cache
def get_database() -> Database:
    return Database(get_settings().database_url)


@lru_cache
def get_weather_adapter() -> WeatherAdapter:
    # Provider 교체 지점 — 기상청/OpenWeather 등은 여기서 구현체만 바꾼다
    settings = get_settings()
    return OpenMeteoAdapter(settings.weather_api_url, settings.weather_timeout_seconds)


@lru_cache
def get_weather_service() -> WeatherService:
    return WeatherService(get_weather_adapter(), get_database(), get_settings())


@lru_cache
def get_weather_scheduler() -> WeatherScheduler:
    return WeatherScheduler(get_weather_service(), get_settings().weather_interval_seconds)


def get_db_session() -> Iterator[Session]:
    session = get_database().session()
    try:
        yield session
    finally:
        session.close()
