# Accuracy Check Scheduler — 공통 IntervalScheduler 상속. Business Logic은 AccuracyCheckService에 있다.
import asyncio

from common.core.scheduler import IntervalScheduler

from services.accuracy_check_service import AccuracyCheckService


class AccuracyCheckScheduler(IntervalScheduler):
    name = "accuracy_check_scheduler"

    def __init__(self, service: AccuracyCheckService, interval_seconds: float, align_offset_seconds: float):
        super().__init__(interval_seconds, align_to_seconds=interval_seconds, align_offset_seconds=align_offset_seconds)
        self._service = service

    async def run_once(self) -> None:
        # S3/RDS 호출은 동기 — 이벤트 루프를 막지 않도록 스레드에서 실행
        await asyncio.to_thread(self._service.check_and_record)
