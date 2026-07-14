# Forecast Scheduler — 공통 IntervalScheduler 상속. Business Logic은 PredictionService에 있다.
import asyncio

from common.core.scheduler import IntervalScheduler

from services.prediction_service import PredictionService


class ForecastScheduler(IntervalScheduler):
    name = "forecast_scheduler"

    def __init__(self, service: PredictionService, interval_seconds: float, align_offset_seconds: float = 0.0):
        super().__init__(interval_seconds, align_to_seconds=interval_seconds, align_offset_seconds=align_offset_seconds)
        self._service = service

    async def run_once(self) -> None:
        # LightGBM/DB/S3는 동기 — 이벤트 루프를 막지 않도록 스레드에서 실행
        await asyncio.to_thread(self._service.run_forecast)
