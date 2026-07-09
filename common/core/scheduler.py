# 공통 Scheduler 베이스 — 향후 weather/forecast/scaler/backup 스케줄러가 모두 이 클래스를 상속한다.
# 새 스케줄러 추가 = "이 클래스 상속 + run_once 구현 + Config 주기 1개" 로 끝나는 구조.
import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from common.core.logger import get_logger

logger = get_logger("scheduler")


class IntervalScheduler(ABC):
    """고정 주기 스케줄러. loop 모드(장기 실행 Pod)와 one-shot 모드(K8s CronJob)를 모두 지원한다.

    run_once에서 예외가 발생해도 루프는 죽지 않고 다음 주기까지 정상 대기한다.
    """

    name: str = "scheduler"

    def __init__(self, interval_seconds: float):
        self._interval = interval_seconds
        self._running = False
        # 상태 조회용 (status API에서 사용)
        self.last_run_at: datetime | None = None
        self.last_success_at: datetime | None = None
        self.last_error: str | None = None
        self.run_count: int = 0
        self.failure_count: int = 0

    @abstractmethod
    async def run_once(self) -> None:
        """1회 실행 본체. 하위 클래스가 구현한다."""

    @property
    def interval_seconds(self) -> float:
        return self._interval

    @property
    def is_running(self) -> bool:
        return self._running

    async def _execute(self) -> None:
        self.last_run_at = datetime.now(timezone.utc)
        self.run_count += 1
        try:
            await self.run_once()
            self.last_success_at = datetime.now(timezone.utc)
            self.last_error = None
        except Exception as exc:  # 스케줄러는 어떤 예외에도 종료되지 않는다
            self.failure_count += 1
            self.last_error = str(exc)
            logger.exception(
                f"{self.name} run failed",
                extra={"event": "scheduler_error", "detail": {"scheduler": self.name}},
            )

    async def run_loop(self) -> None:
        self._running = True
        logger.info(
            f"{self.name} started",
            extra={
                "event": "scheduler_started",
                "detail": {"scheduler": self.name, "interval": self._interval},
            },
        )
        while self._running:
            started = time.monotonic()
            await self._execute()
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(0.0, self._interval - elapsed))
        logger.info(f"{self.name} stopped", extra={"event": "scheduler_stopped"})

    async def run_one_shot(self) -> None:
        """K8s CronJob용 1회 실행."""
        await self._execute()

    def stop(self) -> None:
        self._running = False
