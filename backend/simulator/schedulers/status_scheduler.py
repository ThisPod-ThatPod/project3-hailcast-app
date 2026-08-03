# Status Scheduler — A2: simulator 상태를 주기적으로 FileStore에 써서, predict/대시보드가
# simulator 프로세스에 실시간 HTTP로 안 물어봐도 되게 한다. simulator는 로컬 전용 툴이라
# 파드로 안 뜨므로, "항상 살아있다고 가정하고 HTTP로 부르는" 구조 자체가 실배포에 안 맞는다.
import asyncio

from common.core.constants import SIMULATOR_STATUS_KEY
from common.core.scheduler import IntervalScheduler
from common.core.store import FileStore

from services.traffic_state import SimulatorState


class StatusScheduler(IntervalScheduler):
    name = "status_scheduler"

    def __init__(self, state: SimulatorState, store: FileStore, interval_seconds: float):
        super().__init__(interval_seconds)
        self._state = state
        self._store = store

    async def run_once(self) -> None:
        await asyncio.to_thread(self._write)

    def _write(self) -> None:
        status = self._state.snapshot()
        self._store.write_json(SIMULATOR_STATUS_KEY, status.model_dump(mode="json"))
