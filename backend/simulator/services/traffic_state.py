# Simulator State Manager — Global Variable 금지, 싱글턴 인스턴스를 DI로 주입한다.
# 모든 상태 변경은 이 클래스의 메서드를 통해서만 수행한다.
import asyncio
import time
import uuid
from datetime import datetime, timezone
from enum import StrEnum

from common.core.metrics import CURRENT_TPS, GENERATOR_RUNNING, metrics
from common.models.status import SimulatorStatus


class TrafficMode(StrEnum):
    CONSTANT = "CONSTANT"
    # 확장 예약: SCENARIO(시나리오 재생), BURST(순간 폭증), PEAK_HOUR(출퇴근 곡선),
    # WEATHER_DRIVEN(날씨 기반), PREDICTION_DRIVEN(예측 기반 자동 TPS)


class GeneratorStatus(StrEnum):
    IDLE = "IDLE"
    RUNNING = "RUNNING"


class SimulatorState:
    """Traffic Generator의 단일 상태 원본 (Single Source of Truth)."""

    def __init__(self, min_tps: float, max_tps: float):
        self._min_tps = min_tps
        self._max_tps = max_tps
        self._lock = asyncio.Lock()
        self._reset_fields()

    def _reset_fields(self) -> None:
        self.current_tps: float = 0.0
        self.running: bool = False
        self.status: GeneratorStatus = GeneratorStatus.IDLE
        self.traffic_mode: TrafficMode = TrafficMode.CONSTANT
        self.task_id: str | None = None
        # 통계 — k6가 직접 call-api를 두드리므로 Python 쪽에서는 더 이상 채워지지 않는다.
        # 실제 트래픽 수치는 predict의 GET /dashboard/traffic-history(DB 기준)를 본다.
        self.generated_request_count: int = 0
        self.success_count: int = 0
        self.fail_count: int = 0
        self.queue_publish_count: int = 0
        self.start_time: datetime | None = None
        self.last_request_time: datetime | None = None
        self._run_started_monotonic: float | None = None
        self._accumulated_runtime: float = 0.0

    # ---------- k6 프로세스 수명주기 ----------
    async def mark_started(self) -> str:
        async with self._lock:
            self.running = True
            self.status = GeneratorStatus.RUNNING
            self.task_id = str(uuid.uuid4())
            self.start_time = datetime.now(timezone.utc)
            self._run_started_monotonic = time.monotonic()
            metrics.increment(GENERATOR_RUNNING)  # Stub: gauge 대체
            return self.task_id

    async def mark_stopped(self) -> None:
        async with self._lock:
            if self._run_started_monotonic is not None:
                self._accumulated_runtime += time.monotonic() - self._run_started_monotonic
                self._run_started_monotonic = None
            self.running = False
            self.status = GeneratorStatus.IDLE
            self.task_id = None

    async def reset(self) -> None:
        """Reset: 통계·TPS·Generator 상태 전체 초기화 (Generator 종료는 Service가 선행 수행)."""
        async with self._lock:
            self._reset_fields()

    # ---------- TPS 제어 ----------
    async def adjust_tps(self, delta: float) -> float:
        async with self._lock:
            self.current_tps = max(self._min_tps, min(self._max_tps, self.current_tps + delta))
            metrics.observe(CURRENT_TPS, self.current_tps)
            return self.current_tps

    # ---------- 통계 기록 (Generator 호출 경로 — 락 없이 단순 증가) ----------
    def record_generated(self) -> None:
        self.generated_request_count += 1
        self.last_request_time = datetime.now(timezone.utc)

    def record_success(self, queued: bool) -> None:
        self.success_count += 1
        if queued:
            self.queue_publish_count += 1

    def record_fail(self) -> None:
        self.fail_count += 1

    # ---------- 조회 ----------
    def uptime_seconds(self) -> float:
        total = self._accumulated_runtime
        if self._run_started_monotonic is not None:
            total += time.monotonic() - self._run_started_monotonic
        return total

    def snapshot(self) -> SimulatorStatus:
        uptime = self.uptime_seconds()
        return SimulatorStatus(
            running=self.running,
            status=self.status,
            traffic_mode=self.traffic_mode,
            current_tps=self.current_tps,
            task_id=self.task_id,
            generated_requests=self.generated_request_count,
            success=self.success_count,
            fail=self.fail_count,
            queue_publish=self.queue_publish_count,
            average_tps=round(self.generated_request_count / uptime, 2) if uptime > 0 else 0.0,
            uptime_seconds=round(uptime, 1),
            started_at=self.start_time,
            last_request_at=self.last_request_time,
        )
