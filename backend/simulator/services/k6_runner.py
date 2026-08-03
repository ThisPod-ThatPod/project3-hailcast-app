# K6 Runner — call-api에 부하를 거는 k6 서브프로세스 수명주기 관리.
# k6는 실행 중 목표 rate를 바꿀 수 없으므로, TPS 변경 시 기존 프로세스를 종료하고 새로 띄운다.
import os
import subprocess
from pathlib import Path

from common.core.exceptions import AppError
from common.core.logger import get_logger

logger = get_logger("k6_runner")

_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "k6" / "call_load.js"
_STOP_TIMEOUT_SECONDS = 10


class K6Runner:
    # target_url: k6가 실제로 때릴 주소. [B-1, 2026-07-24] call-api 직결이 아니라
    # simulator 자신의 relay 엔드포인트(SimulatorSettings.relay_url)를 받는다 —
    # call-api로의 실제 전달은 relay 안에서 SimulatorService가 처리한다.
    def __init__(self, target_url: str, k6_binary: str = "k6"):
        self._target_url = target_url
        self._binary = k6_binary
        self._process: subprocess.Popen | None = None

    @property
    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, target_rps: float, current_rps: float = 0.0) -> None:
        """target_rps로 k6를 (재)시작한다. 이미 떠 있으면 먼저 종료 후 새로 띄운다.

        [2026-07-28] current_rps(재시작 직전 rate)를 CURRENT_RPS로 같이 넘긴다 —
        call_load.js가 ramping-arrival-rate로 current_rps→target_rps를 몇 초에 걸쳐
        부드럽게 램프하기 위함(예전엔 constant-arrival-rate라 재시작마다 target으로
        즉시 점프해서, 클릭할 때마다 그래프가 계단식으로 튀는 원인이었다).

        실패 시 호출부가 원인을 알 수 있도록 AppError로 감싼다 — 여기서 실패하면 self._process는
        None으로 남아 running=false와 실제 상태가 일치한다 (target tps만 앞서 갱신돼 있을 수 있음).
        """
        self.stop()
        env = {
            **os.environ,
            "TARGET_URL": self._target_url,
            "TARGET_RPS": f"{target_rps:g}",
            "CURRENT_RPS": f"{current_rps:g}",
        }
        try:
            self._process = subprocess.Popen(
                [self._binary, "run", str(_SCRIPT_PATH)],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            logger.error(
                f"k6 실행 실패 (binary={self._binary}): {exc}",
                extra={"event": "k6_start_failed", "detail": {"binary": self._binary}},
            )
            raise AppError(
                f"k6 실행 파일을 찾을 수 없거나 실행할 수 없습니다 (binary={self._binary}): {exc}",
                detail={"binary": self._binary},
            ) from exc
        logger.info(
            f"k6 started (rps={target_rps:g}, pid={self._process.pid})",
            extra={"event": "k6_started", "detail": {"rps": target_rps}},
        )

    def stop(self) -> None:
        if not self.is_alive:
            self._process = None
            return
        pid = self._process.pid
        self._process.terminate()
        try:
            self._process.wait(timeout=_STOP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            logger.warning(f"k6(pid={pid}) 정상 종료 실패, kill", extra={"event": "k6_kill"})
            self._process.kill()
            self._process.wait(timeout=_STOP_TIMEOUT_SECONDS)
        logger.info(f"k6 stopped (pid={pid})", extra={"event": "k6_stopped"})
        self._process = None
