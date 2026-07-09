# SimulatorService — Simulator Business Logic (start/stop/increase/decrease/reset/status)
import asyncio

from common.core.logger import get_logger
from common.models.status import SimulatorStatus

from config import SimulatorSettings
from services.request_generator import RequestGenerator
from services.traffic_generator import TrafficGenerator
from services.traffic_state import SimulatorState

logger = get_logger("simulator_service")


class SimulatorService:
    def __init__(self, state: SimulatorState, settings: SimulatorSettings):
        self._state = state
        self._settings = settings
        self._control_lock = asyncio.Lock()  # start/stop/reset 동시 호출 직렬화

    async def start(self) -> SimulatorStatus:
        async with self._control_lock:
            if self._state.running:
                # 중복 실행 금지 — 현재 상태만 반환
                logger.info("start ignored, already running", extra={"event": "traffic_started"})
                return self._state.snapshot()
            generator = TrafficGenerator(
                self._state,
                RequestGenerator(self._settings.random_seed),
                self._settings,
            )
            task = asyncio.create_task(generator.run(), name="traffic-generator")
            task_id = await self._state.mark_started(task)
            logger.info(
                "traffic started",
                extra={
                    "event": "traffic_started",
                    "detail": {"task_id": task_id, "tps": self._state.current_tps},
                },
            )
            return self._state.snapshot()

    async def stop(self) -> SimulatorStatus:
        async with self._control_lock:
            await self._stop_generator()
            return self._state.snapshot()

    async def _stop_generator(self) -> None:
        """Generator를 안전하게 종료한다 (cancel 강제 종료 금지 — 루프 스스로 종료)."""
        if not self._state.running and self._state.task is None:
            return
        task = self._state.task
        await self._state.mark_stopping()
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=self._settings.request_timeout_seconds + 5)
            except asyncio.TimeoutError:
                logger.warning("generator drain timeout, cancelling", extra={"event": "traffic_stopped"})
                task.cancel()
        await self._state.mark_stopped()
        logger.info("traffic stopped", extra={"event": "traffic_stopped"})

    async def increase(self) -> SimulatorStatus:
        tps = await self._state.adjust_tps(+self._settings.traffic_step)
        logger.info(f"tps changed to {tps}", extra={"event": "tps_changed", "detail": {"tps": tps}})
        return self._state.snapshot()

    async def decrease(self) -> SimulatorStatus:
        tps = await self._state.adjust_tps(-self._settings.traffic_step)
        logger.info(f"tps changed to {tps}", extra={"event": "tps_changed", "detail": {"tps": tps}})
        return self._state.snapshot()

    async def reset(self) -> SimulatorStatus:
        """Generator 종료 → Task 제거 → TPS=0 → 통계·상태 초기화."""
        async with self._control_lock:
            await self._stop_generator()
            await self._state.reset()
            logger.info("simulator reset", extra={"event": "simulator_reset"})
            return self._state.snapshot()

    def status(self) -> SimulatorStatus:
        return self._state.snapshot()

    async def shutdown(self) -> None:
        """앱 종료(lifespan) 시 Generator 정리."""
        async with self._control_lock:
            await self._stop_generator()
