# SimulatorService — Simulator Business Logic (start/stop/increase/decrease/reset/status)
# 실제 부하는 K6Runner가 띄우는 k6 서브프로세스가 만든다. k6는 실행 중 rate를 못 바꾸므로
# increase/decrease는 새 목표 TPS로 재시작한다(재시작 사이 짧은 공백은 감수).
import asyncio

from common.core.logger import get_logger
from common.models.status import SimulatorStatus

from config import SimulatorSettings
from services.k6_runner import K6Runner
from services.traffic_state import SimulatorState

logger = get_logger("simulator_service")


class SimulatorService:
    def __init__(self, state: SimulatorState, runner: K6Runner, settings: SimulatorSettings):
        self._state = state
        self._runner = runner
        self._settings = settings
        self._control_lock = asyncio.Lock()  # start/stop/increase/decrease/reset 동시 호출 직렬화

    async def start(self) -> SimulatorStatus:
        async with self._control_lock:
            if self._state.running:
                logger.info("start ignored, already running", extra={"event": "traffic_started"})
                return self._state.snapshot()
            tps = self._state.current_tps
            if tps <= 0:
                tps = await self._state.adjust_tps(self._settings.traffic_step)
            await self._start_k6(tps)
            return self._state.snapshot()

    async def stop(self) -> SimulatorStatus:
        async with self._control_lock:
            await self._stop_k6()
            return self._state.snapshot()

    async def _start_k6(self, tps: float) -> None:
        await asyncio.to_thread(self._runner.start, tps)
        task_id = await self._state.mark_started()
        logger.info(
            "traffic started",
            extra={"event": "traffic_started", "detail": {"task_id": task_id, "tps": tps}},
        )

    async def _stop_k6(self) -> None:
        if not self._state.running:
            return
        await asyncio.to_thread(self._runner.stop)
        await self._state.mark_stopped()
        logger.info("traffic stopped", extra={"event": "traffic_stopped"})

    async def increase(self) -> SimulatorStatus:
        async with self._control_lock:
            before = self._state.current_tps
            tps = await self._state.adjust_tps(+self._settings.traffic_step)
            if tps != before:  # 이미 상한(step==max_tps)이면 재시작 안 함 — 클릭해도 no-op
                await self._apply_rate(tps)
            return self._state.snapshot()

    async def decrease(self) -> SimulatorStatus:
        async with self._control_lock:
            before = self._state.current_tps
            tps = await self._state.adjust_tps(-self._settings.traffic_step)
            if tps != before:  # 이미 하한(0)이면 재시작 안 함 — 클릭해도 no-op
                await self._apply_rate(tps)
            return self._state.snapshot()

    async def _apply_rate(self, tps: float) -> None:
        """목표 TPS 변경을 k6에 반영한다. 0 이하가 되면 프로세스를 정지한다."""
        if tps <= 0:
            await self._stop_k6()
            return
        if not self._state.running:
            await self._start_k6(tps)
            return
        # 이미 떠 있던 경우 — 새 rate로 재시작만 하고 시작 시각(task_id 등)은 유지한다.
        await asyncio.to_thread(self._runner.start, tps)
        logger.info(f"tps changed to {tps}", extra={"event": "tps_changed", "detail": {"tps": tps}})

    async def reset(self) -> SimulatorStatus:
        """k6 정지 → 통계·상태 초기화."""
        async with self._control_lock:
            await self._stop_k6()
            await self._state.reset()
            logger.info("simulator reset", extra={"event": "simulator_reset"})
            return self._state.snapshot()

    def status(self) -> SimulatorStatus:
        return self._state.snapshot()

    async def shutdown(self) -> None:
        """앱 종료(lifespan) 시 k6 프로세스를 정리한다."""
        async with self._control_lock:
            await self._stop_k6()
