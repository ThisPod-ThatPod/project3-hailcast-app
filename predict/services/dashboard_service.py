# DashboardService — Frontend 통합 상태 조회 Business Logic
# 각 컴포넌트 조회가 실패해도 나머지 항목은 반환한다 (부분 장애 허용).
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import func, select

from common.aws.sqs_adapter import SqsAdapter
from common.core.logger import get_logger
from common.db.database import Database
from common.db.entities import Call, Weather
from common.models.dashboard import (
    DashboardSummary,
    PredictionSummary,
    ScalingSummary,
    TrafficPoint,
    TrafficStatus,
    WeatherSummary,
    WorkerStatus,
)

from repositories.call_repository import CallRepository

from config import PredictSettings
from repositories.prediction_repository import PredictionRepository
from services.scaler_service import ScalerService

logger = get_logger("dashboard_service")


class DashboardService:
    def __init__(
        self,
        database: Database,
        sqs: SqsAdapter,
        scaler: ScalerService,
        settings: PredictSettings,
    ):
        self._db = database
        self._sqs = sqs
        self._scaler = scaler
        self._settings = settings

    # ---------- 개별 위젯 ----------
    def traffic(self) -> TrafficStatus:
        """Simulator 상태 — Simulator API 프록시 (상태의 원본은 Simulator 프로세스)."""
        try:
            response = httpx.get(
                f"{self._settings.simulator_url}/simulator/status",
                timeout=self._settings.dashboard_proxy_timeout_seconds,
            )
            response.raise_for_status()
            data = response.json()
            return TrafficStatus(
                available=True,
                running=data.get("running"),
                current_tps=data.get("current_tps"),
                generated_requests=data.get("generated_requests"),
                success=data.get("success"),
                fail=data.get("fail"),
                uptime_seconds=data.get("uptime_seconds"),
            )
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning(f"simulator unreachable: {exc}", extra={"event": "dashboard_partial"})
            return TrafficStatus(available=False)

    def prediction(self) -> PredictionSummary:
        with self._db.session_scope() as session:
            repo = PredictionRepository(session)
            generated_at = repo.latest_generated_at()
            if generated_at is None:
                return PredictionSummary(available=False)
            batch = repo.get_batch(generated_at)
        first_target = min(p.target_time for p in batch)
        return PredictionSummary(
            available=True,
            total_predicted_demand=round(
                sum(p.predicted_demand for p in batch if p.target_time == first_target), 2
            ),
            generated_at=generated_at,
            model_version=batch[0].model_version,
            prediction_window_minutes=batch[0].prediction_window_minutes,
            horizon_steps=len({p.target_time for p in batch}),
        )

    def weather(self) -> WeatherSummary:
        with self._db.session_scope() as session:
            latest_time = (
                select(Weather.zone_id, func.max(Weather.observed_at).label("max_time"))
                .where(Weather.data_type == "current")
                .group_by(Weather.zone_id)
                .subquery()
            )
            rows = list(
                session.execute(
                    select(Weather).join(
                        latest_time,
                        (Weather.zone_id == latest_time.c.zone_id)
                        & (Weather.observed_at == latest_time.c.max_time),
                    )
                ).scalars()
            )
        if not rows:
            return WeatherSummary(available=False)
        temps = [w.temperature_c for w in rows if w.temperature_c is not None]
        hums = [w.humidity_pct for w in rows if w.humidity_pct is not None]
        return WeatherSummary(
            available=True,
            latest_observed_at=max(w.observed_at for w in rows),
            zones=len(rows),
            avg_temperature_c=round(sum(temps) / len(temps), 1) if temps else None,
            avg_humidity_pct=round(sum(hums) / len(hums), 1) if hums else None,
            raining_zones=sum(1 for w in rows if (w.rain_mm or 0) > 0),
        )

    def scaling(self) -> ScalingSummary:
        try:
            current = self._scaler.preview()["current_replicas"]
        except Exception:
            current = None
        last_action = None
        with self._db.session_scope() as session:
            from repositories.scaling_repository import ScalingRepository

            events = ScalingRepository(session).get_history(1)
            if events:
                last_action = events[0].action
        return ScalingSummary(
            current_replicas=current,
            keda_enabled=self._settings.keda_enabled,
            last_action=last_action,
            last_predicted_demand=self._scaler.last_predicted_demand,
            last_scaling_at=self._scaler.last_scaling_at,
            cooldown_remaining_seconds=round(self._scaler.cooldown_remaining(), 1),
        )

    def worker(self) -> WorkerStatus:
        backlog = in_flight = None
        try:
            attrs = self._sqs.queue_attributes()
            backlog = int(attrs.get("ApproximateNumberOfMessages", 0))
            in_flight = int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
        except Exception as exc:
            logger.warning(f"queue unreachable: {exc}", extra={"event": "dashboard_partial"})
        since = datetime.now(timezone.utc) - timedelta(minutes=5)
        with self._db.session_scope() as session:
            processed_total = session.execute(
                select(func.count(Call.id)).where(Call.status == "DONE")
            ).scalar_one()
            failed_total = session.execute(
                select(func.count(Call.id)).where(Call.status == "FAILED")
            ).scalar_one()
            recent = session.execute(
                select(func.count(Call.id)).where(Call.status == "DONE", Call.processed_at >= since)
            ).scalar_one()
            avg_latency = session.execute(
                select(
                    func.avg(
                        func.extract("epoch", Call.processed_at) - func.extract("epoch", Call.enqueued_at)
                    )
                ).where(Call.status == "DONE", Call.processed_at >= since)
            ).scalar_one()
        return WorkerStatus(
            queue_backlog=backlog,
            queue_in_flight=in_flight,
            processed_total=processed_total,
            processed_last_5min=recent,
            failed_total=failed_total,
            avg_process_latency_ms=round(avg_latency * 1000, 1) if avg_latency is not None else None,
        )

    def traffic_history(self, minutes: int, bucket_seconds: int) -> list[TrafficPoint]:
        """최근 minutes분간 call-api 수신 요청 수를 bucket_seconds 단위로 집계 (트래픽 추이 그래프)."""
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        with self._db.session_scope() as session:
            buckets = CallRepository(session).traffic_history(since, bucket_seconds)

        first_bucket_epoch = since.timestamp() - (since.timestamp() % bucket_seconds)
        bucket_count = int(minutes * 60 / bucket_seconds) + 1
        points = []
        for i in range(bucket_count):
            bucket = datetime.fromtimestamp(
                first_bucket_epoch + i * bucket_seconds, tz=timezone.utc
            )
            points.append(TrafficPoint(timestamp=bucket, requests=buckets.get(bucket, 0)))
        return points

    # ---------- Summary ----------
    def summary(self, overall_health: str) -> DashboardSummary:
        with self._db.session_scope() as session:
            total_calls = session.execute(select(func.count(Call.id))).scalar_one()
        return DashboardSummary(
            timestamp=datetime.now(timezone.utc),
            health=overall_health,
            traffic=self.traffic(),
            prediction=self.prediction(),
            weather=self.weather(),
            scaling=self.scaling(),
            worker=self.worker(),
            total_calls=total_calls,
        )
