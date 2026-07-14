# Traffic Flush Scheduler — A1: 10초마다 이 파드의 콜 카운트를 FileStore shard로 내보낸다.
import asyncio

from common.core.scheduler import IntervalScheduler

from services.traffic_counter import TrafficCounter


class TrafficFlushScheduler(IntervalScheduler):
    name = "traffic_flush_scheduler"

    def __init__(self, counter: TrafficCounter, interval_seconds: float):
        super().__init__(interval_seconds)
        self._counter = counter

    async def run_once(self) -> None:
        await asyncio.to_thread(self._counter.flush)
