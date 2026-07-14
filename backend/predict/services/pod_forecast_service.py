# PodForecastService — Dashboard "예측 파드 수 vs 실제 파드 수" 그래프 Business Logic
#
# 시간 구간별 데이터 출처:
#   - 과거(bucket < 현재 정시)  : dashboard/pod-history.json (BackupScheduler가 매시 정각 스냅샷)
#   - 현재(bucket == 현재 정시) : predictions/latest.json(실시간) + KedaAdapter 실제 파드 수(실시간)
#   - 미래(bucket > 현재 정시)  : predictions/latest.json의 해당 horizon step (predicted만, actual 없음)
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from common.core.logger import get_logger
from common.core.store import FileStore
from common.models.dashboard import PodForecastPoint
from common.models.prediction import PredictionDocument
from common.models.scaling import ScalingSignals

from adapters.keda_adapter import KedaAdapter
from services.prediction_reader import PredictionReader
from services.scaling_decision_engine import ScalingDecisionEngine

logger = get_logger("pod_forecast_service")

_POD_HISTORY_KEY = "dashboard/pod-history.json"
_HISTORY_MAX_POINTS = 24 * 30  # 1시간 버킷 기준 30일치


def _floor_to_hour(ts: datetime) -> datetime:
    return ts.replace(minute=0, second=0, microsecond=0)


class PodForecastService:
    def __init__(
        self,
        store: FileStore,
        reader: PredictionReader,
        engine: ScalingDecisionEngine,
        keda: KedaAdapter,
        settings,
    ):
        self._store = store
        self._reader = reader
        self._engine = engine
        self._keda = keda
        self._settings = settings

    # ---------- 예측 문서 → replica 변환 ----------
    def _predicted_replicas_for(self, demand: float) -> int:
        return self._engine.decide(ScalingSignals(predicted_demand=demand)).desired_replicas

    def _group_by_target_time(self, document: PredictionDocument) -> dict[datetime, float]:
        totals: dict[datetime, float] = defaultdict(float)
        for item in document.predictions:
            totals[item.target_time] += item.predicted_demand
        return totals

    def _nearest_total(self, totals: dict[datetime, float], bucket: datetime) -> float | None:
        """가장 가까운 target_time을 버킷에 매칭한다 (허용오차=window 크기)."""
        if not totals:
            return None
        closest = min(totals, key=lambda t: abs(t - bucket))
        tolerance = timedelta(minutes=self._settings.prediction_window_minutes)
        if abs(closest - bucket) > tolerance:
            return None
        return totals[closest]

    # ---------- BackupScheduler가 매시 정각 호출 ----------
    def snapshot_current_hour(self) -> None:
        bucket = _floor_to_hour(datetime.now(timezone.utc))

        predicted_replicas: int | None = None
        model_version: str | None = None
        document = self._reader.read_latest()
        if document is not None:
            # 07-13 네이밍 규약에 따른 변수명 및 코드 수정 중 1. 예측 지표 이름 불일치
            # predicted_replicas = self._predicted_replicas_for(document.total_predicted_demand)
            predicted_replicas = self._predicted_replicas_for(document.predicted_taxi_demand)
            model_version = document.model_version

        actual_replicas: int | None = None
        try:
            actual_replicas = self._keda.get_actual_replicas()
        except Exception as exc:
            logger.warning(f"actual replica scrape failed: {exc}", extra={"event": "pod_backup_partial"})

        history = self._store.read_json(_POD_HISTORY_KEY) or []
        bucket_iso = bucket.isoformat()
        history = [h for h in history if h["bucket_time"] != bucket_iso]
        history.append(
            {
                "bucket_time": bucket_iso,
                "predicted_replicas": predicted_replicas,
                "actual_replicas": actual_replicas,
                "model_version": model_version,
            }
        )
        history.sort(key=lambda h: h["bucket_time"])
        history = history[-_HISTORY_MAX_POINTS:]
        self._store.write_json(_POD_HISTORY_KEY, history)
        logger.info(
            f"pod history snapshot saved (bucket={bucket_iso}, "
            f"predicted={predicted_replicas}, actual={actual_replicas})",
            extra={"event": "pod_backup_saved"},
        )

    # ---------- Dashboard 조회 ----------
    def pod_forecast(self, hours_history: int, hours_forecast: int) -> list[PodForecastPoint]:
        now_bucket = _floor_to_hour(datetime.now(timezone.utc))
        start = now_bucket - timedelta(hours=hours_history)

        history = self._store.read_json(_POD_HISTORY_KEY) or []
        history_by_bucket = {}
        for h in history:
            bucket_time = datetime.fromisoformat(h["bucket_time"])
            if start <= bucket_time <= now_bucket:
                history_by_bucket[bucket_time] = (h["predicted_replicas"], h["actual_replicas"])

        document = self._reader.read_latest()
        totals_by_target = self._group_by_target_time(document) if document is not None else {}

        points: list[PodForecastPoint] = []
        for offset in range(-hours_history, hours_forecast + 1):
            bucket = now_bucket + timedelta(hours=offset)
            if bucket < now_bucket:
                predicted, actual = history_by_bucket.get(bucket, (None, None))
            elif bucket == now_bucket:
                predicted = (
                    # 07-13 네이밍 규약에 따른 변수명 및 코드 수정 중 1. 예측 지표 이름 불일치
                    # self._predicted_replicas_for(document.total_predicted_demand)
                    self._predicted_replicas_for(document.predicted_taxi_demand)
                    if document is not None
                    else None
                )
                try:
                    actual = self._keda.get_actual_replicas()
                except Exception:
                    actual = None
            else:
                demand = self._nearest_total(totals_by_target, bucket)
                predicted = self._predicted_replicas_for(demand) if demand is not None else None
                actual = None
            points.append(PodForecastPoint(timestamp=bucket, predicted=predicted, actual=actual))
        return points
