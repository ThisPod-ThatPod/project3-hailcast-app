# Traffic Generator — asyncio Background Task 기반 Traffic Engine.
# 매 tick마다 State의 current_tps를 다시 읽으므로 TPS 변경이 Task 재생성 없이 즉시 반영된다.
# 향후 모드 확장(BURST/PEAK_HOUR/WEATHER_DRIVEN 등)은 _tps_for_tick()만 오버라이드하면 된다.
import asyncio
import time

import httpx

from common.core.logger import get_logger
from common.core.metrics import (
    GENERATION_LATENCY_SECONDS,
    TRAFFIC_FAILED_TOTAL,
    TRAFFIC_GENERATED_TOTAL,
    metrics,
)

from config import SimulatorSettings
from services.request_generator import RequestGenerator
from services.traffic_state import SimulatorState

logger = get_logger("traffic_generator")


class TrafficGenerator:
    def __init__(
        self,
        state: SimulatorState,
        request_generator: RequestGenerator,
        settings: SimulatorSettings,
    ):
        self._state = state
        self._requests = request_generator
        self._settings = settings
        self._semaphore = asyncio.Semaphore(settings.max_in_flight)
        self._in_flight: set[asyncio.Task] = set()

    def _tps_for_tick(self) -> float:
        """이번 tick에 적용할 TPS. 모드별 트래픽 곡선은 여기서 확장한다 (현재 CONSTANT)."""
        return self._state.current_tps

    async def run(self) -> None:
        """Generator 본체. 예외가 발생해도 루프는 계속된다 (Task 전체 종료 금지)."""
        tick = self._settings.generator_tick_seconds
        quota = 0.0  # 소수 TPS 누적 (예: TPS=5, tick=0.2s → 매 tick 1건)
        logger.info(
            "generator loop entered",
            extra={"event": "generator_running", "detail": {"tick": tick}},
        )
        async with httpx.AsyncClient(
            base_url=self._settings.call_api_url,
            timeout=self._settings.request_timeout_seconds,
        ) as client:
            while self._state.running:
                tick_started = time.monotonic()
                try:
                    quota += self._tps_for_tick() * tick
                    to_fire = int(quota)
                    quota -= to_fire
                    for _ in range(to_fire):
                        task = asyncio.create_task(self._fire_one(client))
                        self._in_flight.add(task)
                        task.add_done_callback(self._in_flight.discard)
                except Exception:
                    # Generator 내부 오류는 기록만 하고 다음 tick 진행
                    logger.exception("generator tick error", extra={"event": "generator_error"})
                elapsed = time.monotonic() - tick_started
                await asyncio.sleep(max(0.0, tick - elapsed))

        # 정지 시 in-flight 요청을 안전하게 마무리 (강제 종료 금지)
        if self._in_flight:
            await asyncio.gather(*self._in_flight, return_exceptions=True)
        logger.info("generator loop exited", extra={"event": "generator_exit"})

    async def _fire_one(self, client: httpx.AsyncClient) -> None:
        async with self._semaphore:
            request = self._requests.generate()
            self._state.record_generated()
            metrics.increment(TRAFFIC_GENERATED_TOTAL)
            started = time.monotonic()
            try:
                response = await client.post("/call", json=request.model_dump(mode="json"))
                metrics.observe(GENERATION_LATENCY_SECONDS, time.monotonic() - started)
                if response.status_code == 202:
                    self._state.record_success(queued=True)
                else:
                    self._state.record_fail()
                    metrics.increment(TRAFFIC_FAILED_TOTAL)
                    logger.warning(
                        f"call api returned {response.status_code}",
                        extra={"event": "generator_error", "status": response.status_code},
                    )
            except httpx.HTTPError as exc:
                self._state.record_fail()
                metrics.increment(TRAFFIC_FAILED_TOTAL)
                logger.error(
                    f"call api request failed: {exc}",
                    extra={"event": "generator_error"},
                )
