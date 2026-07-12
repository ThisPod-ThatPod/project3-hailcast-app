# Backup Scheduler — 매시 정각 버킷에 예측/실제 파드 수 스냅샷 저장 (Dashboard 그래프 과거 구간 소스)
import asyncio

from common.core.scheduler import IntervalScheduler

from services.pod_forecast_service import PodForecastService


class BackupScheduler(IntervalScheduler):
    name = "backup_scheduler"

    def __init__(self, service: PodForecastService, interval_seconds: float):
        super().__init__(interval_seconds)
        self._service = service

    async def run_once(self) -> None:
        # DB/S3/K8s 호출은 동기 — 이벤트 루프를 막지 않도록 스레드에서 실행
        await asyncio.to_thread(self._service.snapshot_current_hour)
