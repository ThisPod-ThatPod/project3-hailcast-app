# SimulatorService — Simulator Business Logic (start/stop/increase/decrease/reset/status)
# 실제 부하는 K6Runner가 띄우는 k6 서브프로세스가 만든다. k6는 실행 중 rate를 못 바꾸므로
# increase/decrease는 새 목표 TPS로 재시작한다(재시작 사이 짧은 공백은 감수).
import asyncio

import httpx

from common.core.logger import get_logger
from common.models.status import SimulatorStatus

from config import SimulatorSettings
from services.k6_runner import K6Runner
from services.traffic_state import SimulatorState

logger = get_logger("simulator_service")

# [B-1] relay_call 전용 커넥션 풀 — max_tps(600)를 감당하려면 httpx 기본값(100/20)으로는 부족.
_RELAY_CLIENT_LIMITS = httpx.Limits(max_connections=200, max_keepalive_connections=100)


class SimulatorService:
    def __init__(self, state: SimulatorState, runner: K6Runner, settings: SimulatorSettings):
        self._state = state
        self._runner = runner
        self._settings = settings
        self._control_lock = asyncio.Lock()  # start/stop/increase/decrease/reset 동시 호출 직렬화
        self._relay_client = httpx.AsyncClient(
            timeout=settings.relay_timeout_seconds, limits=_RELAY_CLIENT_LIMITS
        )

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
            was_running = self._state.running
            before = self._state.current_tps
            tps = await self._state.adjust_tps(+self._settings.traffic_step)
            # [B-2, 2026-07-24] tps가 안 바뀌어도(이미 상한) stop() 이후라 안 도는 중이면
            # 재시작해야 한다 — stop()이 current_tps를 리셋 안 하기 때문에, 예전엔 상한에서
            # stop 후 increase를 눌러도 tps==before라 아무 반응이 없었다(진짜 버그).
            if tps != before or not was_running:
                await self._apply_rate(tps)
            return self._state.snapshot()

    async def decrease(self) -> SimulatorStatus:
        async with self._control_lock:
            was_running = self._state.running
            before = self._state.current_tps
            tps = await self._state.adjust_tps(-self._settings.traffic_step)
            if tps != before or not was_running:  # 이유는 increase()와 동일 (B-2)
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

    async def relay_call(self, body: bytes) -> tuple[int, bytes]:
        """[B-1, 2026-07-24] k6가 보낸 요청을 이 자리에서 실제 call-api로 전달하고,
        성공/실패를 그 자리에서 카운트한다(traffic_state.py record_success/record_fail).

        _control_lock을 안 쓴다 — 이건 초당 수백 건 호출되는 고빈도 경로라 start/stop/increase
        같은 저빈도 제어 동작과 직렬화하면 그 자체가 병목이 된다. 통계 카운터는 원래도 락 없이
        단순 증가로 설계돼 있다(traffic_state.py record_generated 주석 참고).
        """
        self._state.record_generated()
        try:
            res = await self._relay_client.post(
                # call_api_url은 클러스터 내부 Service 주소라 ALB를 안 타지만, /api 접두어는
                # ALB가 아니라 call-api 앱이 갖고 있다(7/23 「나」안). 경로는 앱 기준으로 맞춘다.
                f"{self._settings.call_api_url}/api/call",
                content=body,
                headers={"Content-Type": "application/json"},
            )
        except httpx.HTTPError as exc:
            self._state.record_fail()
            logger.warning(f"relay to call-api failed: {exc}", extra={"event": "relay_failed"})
            return 502, b'{"detail":"relay to call-api failed"}'
        if res.status_code == 202:
            self._state.record_success(queued=True)
        elif res.status_code < 400:
            self._state.record_success(queued=False)
        else:
            self._state.record_fail()
        return res.status_code, res.content

    async def shutdown(self) -> None:
        """앱 종료(lifespan) 시 k6 프로세스 + relay HTTP 커넥션 풀을 정리한다."""
        async with self._control_lock:
            await self._stop_k6()
        await self._relay_client.aclose()
