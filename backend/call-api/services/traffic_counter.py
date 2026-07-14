# TrafficCounter — A1 생산 측. 이 파드가 받은 콜 수를 세어뒀다가 주기적으로 FileStore에
# shard 파일로 쓴다. predict의 TrafficAggregatorService가 traffic/instances/ 밑 모든
# 파드의 파일을 모아 합산하므로, call-api가 몇 개 파드로 뜨든 프론트가 보는 숫자는 하나로 합쳐진다.
import threading
import uuid
from datetime import datetime, timezone

from common.core.constants import TRAFFIC_INSTANCE_PREFIX
from common.core.store import FileStore

_INSTANCE_ID = uuid.uuid4().hex[:12]  # 파드마다 고유 — 프로세스 기동 시 1회 생성


class TrafficCounter:
    def __init__(self, store: FileStore):
        self._store = store
        self._lock = threading.Lock()
        self._count = 0

    def record(self) -> None:
        with self._lock:
            self._count += 1

    def flush(self) -> None:
        """카운트를 읽고 0으로 리셋한 뒤 FileStore에 쓴다.

        count=0이어도 매번 쓴다 — updated_at이 갱신돼야 "이 파드는 살아있다"는 하트비트가
        되고, predict가 오래 안 갱신된 파일을 죽은 파드로 보고 집계에서 제외하기 때문이다.
        """
        with self._lock:
            count = self._count
            self._count = 0
        self._store.write_json(
            f"{TRAFFIC_INSTANCE_PREFIX}{_INSTANCE_ID}.json",
            {"count": count, "updated_at": datetime.now(timezone.utc).isoformat()},
        )
