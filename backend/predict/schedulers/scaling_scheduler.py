# Scaling Scheduler — Prediction Interval과 독립된 주기로 동작 (SCALING_INTERVAL_SECONDS)
import asyncio

from common.core.scheduler import IntervalScheduler

from services.scaler_service import ScalerService


class ScalingScheduler(IntervalScheduler):
    name = "scaling_scheduler"

    def __init__(self, service: ScalerService, interval_seconds: float):
        super().__init__(interval_seconds)
        self._service = service

    async def run_once(self) -> None:
        # S3/DB/K8s 호출은 동기 — 이벤트 루프를 막지 않도록 스레드에서 실행
        await asyncio.to_thread(self._service.run_scaling)
