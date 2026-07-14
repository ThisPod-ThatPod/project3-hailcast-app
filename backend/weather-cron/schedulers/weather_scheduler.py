# Weather Scheduler — 공통 IntervalScheduler 상속. UTC 자정 기준 4시간 단위로 정렬 실행된다.
from common.core.scheduler import IntervalScheduler

from services.weather_service import WeatherService


class WeatherScheduler(IntervalScheduler):
    name = "weather_scheduler"

    def __init__(self, service: WeatherService, interval_seconds: float, align_offset_seconds: float = 0.0):
        super().__init__(interval_seconds, align_to_seconds=interval_seconds, align_offset_seconds=align_offset_seconds)
        self._service = service

    async def run_once(self) -> None:
        await self._service.collect()
