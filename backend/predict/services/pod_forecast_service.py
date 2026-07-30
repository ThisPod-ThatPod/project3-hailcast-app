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
        # [2026-07-30] 경계값(정확히 tolerance만큼 차이)도 탈락시킨다 — horizon 마지막 시간창
        # 값을 그다음 시간 칸까지 "빌려와" 채우는 현상(대시보드 그래프 +5h 칸에 +4h 값 재사용)
        # 방지. 일반적인 정시 매칭(차이=0)에는 영향 없다.
        if abs(closest - bucket) >= tolerance:
            return None
        return totals[closest]

    def _predicted_for_bucket(self, document: PredictionDocument | None, bucket: datetime) -> int | None:
        """[B-3, 2026-07-24] 그 버킷(target_time)에 대해 실제로 만들어진 예측을 찾는다.

        예전엔 이 자리에서 document.predicted_taxi_demand(그 문서의 '첫 번째' 시간창 값,
        생성 시점 기준)를 그대로 썼다 — prediction_interval_seconds(4시간) 주기라, 새 문서가
        아직 안 나온 시간대엔 "지금 이 시간을 위해 미리 만든 예측"이 아니라 "그 순간 기준
        가장 최신 예측"이 찍혀서, 사실상 actual과 거의 같은 신호를 두 번 찍는 꼴이었다.
        미래 버킷(pod_forecast의 else 분기)과 동일하게 target_time 매칭으로 통일한다.
        """
        if document is None:
            return None
        totals = self._group_by_target_time(document)
        demand = self._nearest_total(totals, bucket)
        if demand is None:
            return None
        return self._predicted_replicas_for(demand)

    # ---------- BackupScheduler가 매시 정각 호출 ----------
    def snapshot_current_hour(self) -> None:
        bucket = _floor_to_hour(datetime.now(timezone.utc))

        predicted_replicas: int | None = None
        model_version: str | None = None
        document = self._reader.read_latest()
        if document is not None:
            predicted_replicas = self._predicted_for_bucket(document, bucket)
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
                predicted = self._predicted_for_bucket(document, bucket)
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
