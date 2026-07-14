# Traffic Scheduler — A1: 10초마다 call-api 파드들의 trafic shard를 모아 집계한다.
import asyncio

from common.core.scheduler import IntervalScheduler

from services.traffic_aggregator_service import TrafficAggregatorService


class TrafficScheduler(IntervalScheduler):
    name = "traffic_scheduler"

    def __init__(self, service: TrafficAggregatorService, interval_seconds: float):
        super().__init__(interval_seconds)
        self._service = service

    async def run_once(self) -> None:
        # S3 백엔드면 list_keys가 네트워크 호출 — 이벤트 루프를 막지 않도록 스레드에서 실행
        await asyncio.to_thread(self._service.aggregate)
