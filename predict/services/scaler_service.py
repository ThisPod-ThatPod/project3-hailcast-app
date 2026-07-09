# ScalerService — Predictive Scaling 오케스트레이션
# Prediction Reader → (Validation/Freshness) → Decision Engine → Cooldown → KEDA Patch [Retry] → History
import time
from datetime import datetime, timezone

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
from common.db.database import Database
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
        database: Database,
        settings: PredictSettings,
    ):
        self._reader = reader
        self._engine = engine
        self._keda = keda
        self._db = database
        self._settings = settings
        # 상태 조회용 (Dashboard /scaling/status)
        self.last_predicted_demand: float | None = None
        self.last_decision: str | None = None
        self.last_scaling_at: datetime | None = None

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
            decision = self._engine.decide(
                ScalingSignals(predicted_demand=document.total_predicted_demand)
            )
            result.update(
                predicted_demand=document.total_predicted_demand,
                desired_replicas=decision.desired_replicas,
                generated_at=document.generated_at,
            )
        return result

    # ---------- Scaling 1회 실행 ----------
    def run_scaling(self) -> None:
        logger.info("scaling started", extra={"event": "scaling_started"})

        # 1) Prediction Load + Schema Validation — 없거나 비정상이면 Scaling 안 함
        document = self._reader.read_latest()
        if document is None:
            logger.warning("no valid prediction, scaling skipped", extra={"event": "scaling_skipped"})
            return

        # 2) Freshness 검증 — 오래된 예측으로 스케일하지 않는다
        age = (datetime.now(timezone.utc) - document.generated_at).total_seconds()
        if age > self._settings.prediction_max_age_seconds:
            logger.warning(
                f"prediction too old ({age:.0f}s), scaling skipped",
                extra={"event": "scaling_skipped", "detail": {"age_seconds": round(age)}},
            )
            return

        demand = document.total_predicted_demand
        self.last_predicted_demand = demand

        # 3) Decision Engine — Replica 계산 (Business Logic은 Engine에만 있다)
        decision = self._engine.decide(ScalingSignals(predicted_demand=demand))
        self.last_decision = decision.matched_rule

        # 4) 현재값 비교
        current = self._with_retry("keda_read", self._keda.get_min_replicas)
        metrics.observe(CURRENT_REPLICA, current)
        if decision.desired_replicas == current:
            logger.info(
                f"replicas unchanged ({current}), rule[{decision.matched_rule}]",
                extra={"event": "scaling_hold", "count": current},
            )
            return

        # 5) Scale Down은 Cooldown 적용 (Scale Up은 선제 확장이므로 즉시)
        if decision.desired_replicas < current:
            remaining = self.cooldown_remaining()
            if remaining > 0:
                logger.info(
                    f"cooldown activated, scale down deferred ({remaining:.0f}s remaining)",
                    extra={"event": "cooldown_activated", "detail": {"remaining": round(remaining)}},
                )
                return

        # 6) KEDA Patch [Retry] + History 저장
        try:
            applied = self._with_retry(
                "keda_patch", lambda: self._keda.patch_min_replicas(decision.desired_replicas)
            )
        except Exception as exc:
            raise ScalingError(f"keda patch failed after retries: {exc}") from exc
        action = "SCALE_UP" if applied > current else "SCALE_DOWN"
        now = datetime.now(timezone.utc)
        self.last_scaling_at = now
        with self._db.session_scope() as session:
            ScalingRepository(session).save_event(
                predicted_demand=demand,
                old_replica=current,
                new_replica=applied,
                action=action,
                reason=decision.reason,
                model_version=document.model_version,
            )
        metrics.increment(SCALING_TOTAL)
        metrics.increment(SCALE_UP_TOTAL if action == "SCALE_UP" else SCALE_DOWN_TOTAL)
        metrics.observe(CURRENT_REPLICA, applied)
        metrics.observe(LAST_SCALING_TIMESTAMP, now.timestamp())
        logger.info(
            f"replica changed {current} -> {applied} ({action})",
            extra={
                "event": "replica_changed",
                "status": action,
                "detail": {"demand": demand, "rule": decision.matched_rule},
            },
        )
