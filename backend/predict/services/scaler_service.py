# ScalerService — Predictive Scaling 오케스트레이션
# Prediction Reader → G1(예측 기준선) → G2(실측 트래픽 반응형 조정+히스테리시스) →
# Cooldown → KEDA Patch [Retry] → RDS 이력(ScalingEvent, 2026-07-20 S3→RDS 컷오버)
import time
from datetime import datetime, timedelta, timezone

from common.core.exceptions import ScalingError
from common.core.logger import get_logger
from common.core.metrics import (
    CURRENT_REPLICA,
    LAST_SCALING_TIMESTAMP,
    SCALE_DOWN_TOTAL,
    SCALE_UP_TOTAL,
    SCALING_TOTAL,
    metrics,
)
from common.core.store import FileStore
from common.db.database import Database
from common.models.prediction import PredictionDocument
from common.models.scaling import ScalingSignals

from adapters.keda_adapter import KedaAdapter
from config import PredictSettings
from repositories.scaling_repository import ScalingRepository
from services.prediction_reader import PredictionReader
from services.scaling_decision_engine import ScalingDecisionEngine

logger = get_logger("scaler_service")


class ScalerService:
    def __init__(
        self,
        reader: PredictionReader,
        engine: ScalingDecisionEngine,
        keda: KedaAdapter,
        store: FileStore,
        database: Database,
        settings: PredictSettings,
    ):
        self._reader = reader
        self._engine = engine
        self._keda = keda
        self._store = store   # G2(실측 트래픽, dashboard/traffic.json) 읽기용 — D-1 확정대로 S3 유지
        self._db = database
        self._settings = settings
        # 상태 조회용 (Dashboard /scaling/status)
        self.last_predicted_demand: float | None = None
        self.last_decision: str | None = None
        self.last_scaling_at: datetime | None = None
        # G2 히스테리시스 — 반응형으로 올라간 뒤 유지 중인 replica 수 (None=반응형 비활성)
        self._reactive_hold_replicas: int | None = None

    # ---------- Retry (KEDA Patch) ----------
    def _with_retry(self, name: str, fn):
        last_exc: Exception | None = None
        for attempt in range(1, self._settings.scaling_retry_count + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    f"{name} retry {attempt}/{self._settings.scaling_retry_count}: {exc}",
                    extra={"event": "patch_failed", "count": attempt, "detail": {"step": name}},
                )
                if attempt < self._settings.scaling_retry_count:
                    time.sleep(self._settings.scaling_retry_backoff_seconds * attempt)
        raise last_exc

    # ---------- Cooldown ----------
    def cooldown_remaining(self) -> float:
        last = self.last_scaling_at
        if last is None:
            with self._db.session_scope() as session:
                last = ScalingRepository(session).last_event_time()
            if last is not None:
                self.last_scaling_at = last
        if last is None:
            return 0.0
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return max(0.0, self._settings.scaling_cooldown_seconds - elapsed)

    # ---------- 조회 (Dashboard /scaling/current) ----------
    def preview(self) -> dict:
        """현재 replica와 최신 예측 기준 목표 replica를 계산만 한다 (Patch 없음)."""
        result: dict = {"current_replicas": self._keda.get_min_replicas()}
        document = self._reader.read_latest()
        if document is not None:
            demand = self._current_demand(document)
            decision = self._engine.decide(ScalingSignals(predicted_demand=demand))
            result.update(
                predicted_demand=demand,
                desired_replicas=decision.desired_replicas,
                generated_at=document.generated_at,
            )
        return result

    def _current_demand(self, document: PredictionDocument) -> float:
        """[2026-07-27] "지금 이 시간"에 해당하는 target_time을 매칭해서 수요를 고른다.

        예전엔 document.predicted_taxi_demand(그 문서의 '첫 번째' 시간창 값, 생성
        시점 기준)를 그대로 썼다 — 예측이 4시간 주기로만 갱신되므로, 갱신 직후가
        아니면 "첫 번째" 항목이 지금 시간과 다른 경우가 대부분이었다.
        pod_forecast_service.py의 대시보드 그래프는 이미 target_time 매칭으로
        고쳤는데(B-3, 2026-07-24) 여기(실제 minReplicaCount를 정하는 스케일링
        결정)는 그대로 남아있어서, 대시보드가 보여주는 "예측파드수"와 실제
        replica 수가 어긋나는 원인이었다 — 둘을 동일한 로직으로 통일한다.
        """
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        totals = {item.target_time: item.predicted_demand for item in document.predictions}
        if not totals:
            return document.predicted_taxi_demand
        closest = min(totals, key=lambda t: abs(t - now))
        tolerance = timedelta(minutes=self._settings.prediction_window_minutes)
        if abs(closest - now) > tolerance:
            return document.predicted_taxi_demand
        return totals[closest]

    # ---------- G2: 실측 트래픽 반응형 조정 ----------
    def _read_actual_traffic(self) -> float | None:
        """A1(트래픽 10초 단위 집계)이 아직 구현 전이면 항상 None → 반응형 레이어 비활성.

        A1 완료 후: dashboard/traffic.json의 예상 스키마는
        {"hourly_requests": <G1과 같은 단위(시간당 수요)로 환산된 실측 트래픽>} — G1의
        scaling_demand_per_pod와 단위가 어긋나면 워터마크 비교가 무의미해지므로, A1
        구현 시 이 단위를 맞추거나 여기 변환 로직을 추가할 것.
        """
        body = self._store.read_json(self._settings.traffic_json_key)
        if not body:
            return None
        return body.get("hourly_requests")

    def _apply_reactive_adjustment(self, baseline: int, current: int) -> tuple[int, str]:
        """G2: 예측 기준선(baseline) 위에 실측 트래픽 워터마크로 ±1 반응형 조정.

        히스테리시스: 반응형으로 한 번 올라가면, 다음 예측 갱신에서 baseline이 더
        낮아져도 즉시 안 낮춘다 — 실측 트래픽이 하한 워터마크 밑으로 내려갈 때까지
        (발동 시점부터 다음 예측 갱신 시점까지 계속) 감시하다가, 안전해지면 그때
        baseline을 채택한다.
        """
        traffic = self._read_actual_traffic()
        if traffic is None:
            self._reactive_hold_replicas = None
            return baseline, self.last_decision or ""

        capacity = current * self._settings.scaling_demand_per_pod
        utilization = traffic / capacity if capacity > 0 else 1.0

        if self._reactive_hold_replicas is not None:
            if utilization <= self._settings.scaling_watermark_low:
                self._reactive_hold_replicas = None  # 해제 — baseline으로 복귀
            else:
                held = max(self._reactive_hold_replicas, baseline)
                return held, f"reactive-hold (util={utilization:.0%})"

        if utilization >= self._settings.scaling_watermark_high:
            bumped = current + self._settings.scaling_reactive_step
            self._reactive_hold_replicas = bumped
            return bumped, f"reactive-up (util={utilization:.0%})"

        if utilization <= self._settings.scaling_watermark_low and baseline < current:
            stepped_down = max(baseline, current - self._settings.scaling_reactive_step)
            return stepped_down, f"reactive-down (util={utilization:.0%})"

        return baseline, self.last_decision or ""

    # ---------- Scaling 1회 실행 ----------
    def run_scaling(self) -> None:
        logger.info("scaling started", extra={"event": "scaling_started"})

        document = self._reader.read_latest()
        if document is None:
            logger.warning("no valid prediction, scaling skipped", extra={"event": "scaling_skipped"})
            return

        age = (datetime.now(timezone.utc) - document.generated_at).total_seconds()
        if age > self._settings.prediction_max_age_seconds:
            logger.warning(
                f"prediction too old ({age:.0f}s), scaling skipped",
                extra={"event": "scaling_skipped", "detail": {"age_seconds": round(age)}},
            )
            return

        demand = self._current_demand(document)
        self.last_predicted_demand = demand

        baseline_decision = self._engine.decide(ScalingSignals(predicted_demand=demand))
        self.last_decision = baseline_decision.matched_rule

        current = self._with_retry("keda_read", self._keda.get_min_replicas)
        metrics.observe(CURRENT_REPLICA, current)

        desired, decision_note = self._apply_reactive_adjustment(baseline_decision.desired_replicas, current)
        self.last_decision = decision_note

        if desired == current:
            logger.info(
                f"replicas unchanged ({current}), rule[{decision_note}]",
                extra={"event": "scaling_hold", "count": current},
            )
            return

        if desired < current:
            remaining = self.cooldown_remaining()
            if remaining > 0:
                logger.info(
                    f"cooldown activated, scale down deferred ({remaining:.0f}s remaining)",
                    extra={"event": "cooldown_activated", "detail": {"remaining": round(remaining)}},
                )
                return

        try:
            applied = self._with_retry(
                "keda_patch", lambda: self._keda.patch_min_replicas(desired)
            )
        except Exception as exc:
            raise ScalingError(f"keda patch failed after retries: {exc}") from exc
        action = "SCALE_UP" if applied > current else "SCALE_DOWN"
        now = datetime.now(timezone.utc)
        self.last_scaling_at = now
        self._save_history_event(demand, current, applied, action, decision_note, document.model_version)
        metrics.increment(SCALING_TOTAL)
        metrics.increment(SCALE_UP_TOTAL if action == "SCALE_UP" else SCALE_DOWN_TOTAL)
        metrics.observe(CURRENT_REPLICA, applied)
        metrics.observe(LAST_SCALING_TIMESTAMP, now.timestamp())
        logger.info(
            f"replica changed {current} -> {applied} ({action})",
            extra={
                "event": "replica_changed",
                "status": action,
                "detail": {"demand": demand, "rule": decision_note},
            },
        )

    def _save_history_event(
        self,
        demand: float,
        old_replica: int,
        new_replica: int,
        action: str,
        reason: str,
        model_version: str | None,
    ) -> None:
        with self._db.session_scope() as session:
            ScalingRepository(session).save_event(
                predicted_demand=demand,
                old_replica=old_replica,
                new_replica=new_replica,
                action=action,
                reason=reason,
                model_version=model_version,
            )
