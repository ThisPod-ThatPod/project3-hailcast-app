# Weather Scheduler — 공통 IntervalScheduler 상속 (loop / one-shot 겸용)
from common.core.scheduler import IntervalScheduler

from services.weather_service import WeatherService


class WeatherScheduler(IntervalScheduler):
    name = "weather_scheduler"

    def __init__(self, service: WeatherService, interval_seconds: float):
        super().__init__(interval_seconds)
        self._service = service

    async def run_once(self) -> None:
        await self._service.collect_all()
