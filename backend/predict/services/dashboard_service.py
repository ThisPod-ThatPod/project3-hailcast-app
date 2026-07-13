# DashboardService — Frontend 통합 상태 조회 Business Logic (H1/H2)
# 파드 수(scaler/KEDA)·트래픽(A1 집계)만 다룬다 — 노드 수는 데이터 소스가 없어 보류(C8).
from datetime import datetime, timedelta, timezone

from common.core.constants import TRAFFIC_HISTORY_KEY
from common.core.logger import get_logger
from common.core.store import FileStore
from common.models.dashboard import DashboardStats, TrafficPoint

from adapters.keda_adapter import KedaAdapter
from config import PredictSettings

logger = get_logger("dashboard_service")


class DashboardService:
    def __init__(self, store: FileStore, keda: KedaAdapter, settings: PredictSettings):
        self._store = store
        self._keda = keda
        self._settings = settings

    def stats(self) -> DashboardStats:
        try:
            pods = self._keda.get_min_replicas()
        except Exception as exc:
            logger.warning(f"keda unreachable: {exc}", extra={"event": "dashboard_partial"})
            pods = None
        traffic_body = self._store.read_json(self._settings.traffic_json_key) or {}
        return DashboardStats(
            pods=pods,
            traffic=int(traffic_body.get("current_bucket_requests", 0)),
            nodes=None,  # C8 — K8s 노드 조회 데이터 소스 없음
        )

    def traffic_history(self, minutes: int, bucket_seconds: int) -> list[TrafficPoint]:
        """A1이 쌓아둔 10초 버킷 원본을 요청받은 (minutes, bucket_seconds)로 다시 묶는다."""
        raw = self._store.read_json(TRAFFIC_HISTORY_KEY) or []
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)

        rebucketed: dict[float, int] = {}
        for point in raw:
            ts = datetime.fromisoformat(point["timestamp"])
            if ts < since:
                continue
            bucket_epoch = ts.timestamp() - (ts.timestamp() % bucket_seconds)
            rebucketed[bucket_epoch] = rebucketed.get(bucket_epoch, 0) + point["requests"]

        first_bucket_epoch = since.timestamp() - (since.timestamp() % bucket_seconds)
        bucket_count = int(minutes * 60 / bucket_seconds) + 1
        points = []
        for i in range(bucket_count):
            epoch = first_bucket_epoch + i * bucket_seconds
            points.append(
                TrafficPoint(
                    timestamp=datetime.fromtimestamp(epoch, tz=timezone.utc),
                    requests=rebucketed.get(epoch, 0),
                )
            )
        return points
