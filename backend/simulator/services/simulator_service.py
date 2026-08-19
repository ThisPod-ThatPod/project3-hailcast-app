# SimulatorService — Simulator Business Logic (start/stop/increase/decrease/reset/status)
# 실제 부하는 K6Runner가 띄우는 k6 서브프로세스가 만든다. k6는 실행 중 rate를 못 바꾸므로
# increase/decrease는 새 목표 TPS로 재시작한다(재시작 사이 짧은 공백은 감수).
import asyncio

import aiohttp

from common.core.logger import get_logger
from common.models.status import SimulatorStatus

from config import SimulatorSettings
from services.k6_runner import K6Runner
from services.traffic_state import SimulatorState

logger = get_logger("simulator_service")

# [2026-08-18, D안] httpx → aiohttp 교체 — 요청당 CPU 오버헤드 실측(~5.83ms)이 커서 격리
# 벤치마크로 재검증 후 교체(docs/2026-08-18-httpx-replace-review.md). limit은 httpx
# max_connections(총 동시 연결)에 대응, limit_per_host는 relay 상대가 call-api 하나뿐이라
# limit과 동일하게 맞춰서 사실상 전체 풀을 이 한 호스트가 다 쓸 수 있게 한다
# (httpx max_keepalive_connections에 1:1 대응하는 옵션은 aiohttp에 없음 — keepalive_timeout으로
# 유휴 커넥션 재사용 창을 대신 조절한다).
_RELAY_CONNECTOR_LIMIT = 200
_RELAY_KEEPALIVE_TIMEOUT_SECONDS = 30.0


class SimulatorService:
    def __init__(self, state: SimulatorState, runner: K6Runner, settings: SimulatorSettings):
        self._state = state
        self._runner = runner
        self._settings = settings
        self._control_lock = asyncio.Lock()  # start/stop/increase/decrease/reset 동시 호출 직렬화
        # [2026-08-19 버그 수정] aiohttp.TCPConnector/ClientSession은 생성 시점에
        # asyncio.get_running_loop()를 직접 호출해서, 실행 중인 이벤트 루프가 없으면
        # RuntimeError를 던진다. httpx.AsyncClient는 이 제약이 없어서 __init__(동기 함수,
        # DI가 스레드풀에서 호출)에서 만들어도 문제없었는데, aiohttp는 그대로 옮기면 매
        # 요청마다 500(get_simulator_service가 @lru_cache라 실패한 인스턴스는 캐시도 안 됨).
        # 그래서 실제로 이벤트 루프 안에서 처음 쓰일 때(relay_call 등 async 메서드 안에서)
        # 지연 생성한다 — 생성 자체엔 await가 없어서 동시 요청이 몰려도 경합 없이 안전하다.
        self._relay_client: aiohttp.ClientSession | None = None

    def _ensure_relay_client(self) -> aiohttp.ClientSession:
        if self._relay_client is None:
            connector = aiohttp.TCPConnector(
                limit=_RELAY_CONNECTOR_LIMIT,
                limit_per_host=_RELAY_CONNECTOR_LIMIT,
                keepalive_timeout=_RELAY_KEEPALIVE_TIMEOUT_SECONDS,
            )
            # httpx timeout=5.0은 connect/read/write/pool 전 구간에 동일하게 적용되는 총
            # 타임아웃이라, 의미가 가장 가까운 aiohttp의 total로 옮긴다.
            timeout = aiohttp.ClientTimeout(total=self._settings.relay_timeout_seconds)
            self._relay_client = aiohttp.ClientSession(connector=connector, timeout=timeout)
        return self._relay_client

    async def start(self) -> SimulatorStatus:
        async with self._control_lock:
            if self._state.running:
                logger.info("start ignored, already running", extra={"event": "traffic_started"})
                return self._state.snapshot()
            tps = self._state.current_tps
            if tps <= 0:
                tps = await self._state.adjust_tps(self._settings.traffic_step)
            await self._start_k6(tps, current_tps=0.0)
            return self._state.snapshot()

    async def stop(self) -> SimulatorStatus:
        async with self._control_lock:
            await self._stop_k6()
            return self._state.snapshot()

    async def _start_k6(self, tps: float, current_tps: float = 0.0) -> None:
        await asyncio.to_thread(self._runner.start, tps, current_tps)
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
                await self._apply_rate(tps, before if was_running else 0.0)
            return self._state.snapshot()

    async def decrease(self) -> SimulatorStatus:
        async with self._control_lock:
            was_running = self._state.running
            before = self._state.current_tps
            tps = await self._state.adjust_tps(-self._settings.traffic_step)
            if tps != before or not was_running:  # 이유는 increase()와 동일 (B-2)
                await self._apply_rate(tps, before if was_running else 0.0)
            return self._state.snapshot()

    async def _apply_rate(self, tps: float, current_tps: float = 0.0) -> None:
        """목표 TPS 변경을 k6에 반영한다. 0 이하가 되면 프로세스를 정지한다.

        current_tps: 재시작 직전(변경 전) rate — k6가 여기서부터 target(tps)까지 부드럽게
        램프하도록 K6Runner에 그대로 전달한다(2026-07-28, 계단식 그래프 문제 완화).
        """
        if tps <= 0:
            await self._stop_k6()
            return
        if not self._state.running:
            await self._start_k6(tps, current_tps)
            return
        # 이미 떠 있던 경우 — 새 rate로 재시작만 하고 시작 시각(task_id 등)은 유지한다.
        await asyncio.to_thread(self._runner.start, tps, current_tps)
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

    _BURST_PAYLOAD = (
        b'{"user_id":"burst","pickup":"burst-pickup",'
        b'"destination":"burst-destination","source":"simulator"}'
    )

    async def burst(self, count: int) -> int:
        """[2026-07-28] N건을 rate 제한 없이 최대한 빠르게(동시성만 제한) call-api로
        쏴서 SQS 큐를 순간적으로 채운다 — 반응형(KEDA) 스케일링 시연용.

        지속형 TPS(increase/decrease, k6)와 별개 경로다. k6/현재 tps 상태는 안 건드리고,
        relay_call()과 동일하게 record_generated/success/fail로 카운트만 같이 늘어난다.
        백그라운드로 던지고 바로 반환 — 수천 건을 동시성 제한 걸고 보내면 수 초~수십 초
        걸릴 수 있어서, 호출부(HTTP 요청)를 그만큼 붙잡아두지 않기 위함이다. 진행 상황은
        기존 /simulator/status의 generated_requests 증가로 확인한다.
        """
        count = max(0, min(count, self._settings.burst_max_count))
        if count == 0:
            return 0
        asyncio.create_task(self._run_burst(count))
        logger.info(f"burst queued (count={count})", extra={"event": "burst_queued", "count": count})
        return count

    async def _run_burst(self, count: int) -> None:
        sem = asyncio.Semaphore(self._settings.burst_concurrency)

        async def one() -> None:
            async with sem:
                await self.relay_call(self._BURST_PAYLOAD)

        await asyncio.gather(*(one() for _ in range(count)))
        logger.info(f"burst finished (count={count})", extra={"event": "burst_finished", "count": count})

    async def relay_call(self, body: bytes) -> tuple[int, bytes]:
        """[B-1, 2026-07-24] k6가 보낸 요청을 이 자리에서 실제 call-api로 전달하고,
        성공/실패를 그 자리에서 카운트한다(traffic_state.py record_success/record_fail).

        _control_lock을 안 쓴다 — 이건 초당 수백 건 호출되는 고빈도 경로라 start/stop/increase
        같은 저빈도 제어 동작과 직렬화하면 그 자체가 병목이 된다. 통계 카운터는 원래도 락 없이
        단순 증가로 설계돼 있다(traffic_state.py record_generated 주석 참고).
        """
        self._state.record_generated()
        try:
            async with self._ensure_relay_client().post(
                # call_api_url은 클러스터 내부 Service 주소라 ALB를 안 타지만, /api 접두어는
                # ALB가 아니라 call-api 앱이 갖고 있다(7/23 「나」안). 경로는 앱 기준으로 맞춘다.
                f"{self._settings.call_api_url}/api/call",
                data=body,
                headers={"Content-Type": "application/json"},
            ) as res:
                status = res.status
                content = await res.read()
        # aiohttp는 타임아웃을 ClientError 계열이 아니라 asyncio.TimeoutError로도 던진다
        # (ClientTimeout 구간에 따라 다름) — httpx.HTTPError 하나로 잡던 것과 동등하게
        # 두 예외를 모두 잡아야 실패가 relay 루프 밖으로 새지 않는다.
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            self._state.record_fail()
            logger.warning(f"relay to call-api failed: {exc}", extra={"event": "relay_failed"})
            return 502, b'{"detail":"relay to call-api failed"}'
        if status == 202:
            self._state.record_success(queued=True)
        elif status < 400:
            self._state.record_success(queued=False)
        else:
            self._state.record_fail()
        return status, content

    async def shutdown(self) -> None:
        """앱 종료(lifespan) 시 k6 프로세스 + relay HTTP 커넥션 풀을 정리한다."""
        async with self._control_lock:
            await self._stop_k6()
        # 한 번도 relay_call()이 안 불려서 지연 생성이 아직 안 됐으면(_ensure_relay_client
        # 미호출) None일 수 있다 — close() 시도하면 AttributeError.
        if self._relay_client is not None:
            await self._relay_client.close()
