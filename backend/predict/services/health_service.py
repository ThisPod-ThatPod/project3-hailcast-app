# HealthService — 컴포넌트별 상태 점검 (healthy | warning | unhealthy)
# DB 없음(J3) — queue(SQS)·model(S3)·prediction/weather(FileStore) 전부 외부 스토어 기준.
import csv
import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from common.aws.s3_adapter import S3Adapter
from common.aws.sqs_adapter import SqsAdapter
from common.core.scheduler import IntervalScheduler
from common.core.store import FileStore
from common.models.dashboard import ComponentHealth, HealthResponse

from config import PredictSettings

HEALTHY, WARNING, UNHEALTHY = "healthy", "warning", "unhealthy"
_SEVERITY = {HEALTHY: 0, WARNING: 1, UNHEALTHY: 2}


class HealthService:
    def __init__(
        self,
        store: FileStore,
        sqs: SqsAdapter,
        s3: S3Adapter,
        schedulers: list[IntervalScheduler],
        settings: PredictSettings,
    ):
        self._store = store
        self._sqs = sqs
        self._s3 = s3
        self._schedulers = schedulers
        self._settings = settings

    # ---------- 개별 점검 ----------
    def _check_queue(self) -> ComponentHealth:
        try:
            attrs = self._sqs.queue_attributes()
            backlog = int(attrs.get("ApproximateNumberOfMessages", 0))
            if backlog > self._settings.health_queue_backlog_warning:
                return ComponentHealth(name="queue", status=WARNING, detail=f"backlog={backlog}")
            return ComponentHealth(name="queue", status=HEALTHY, detail=f"backlog={backlog}")
        except Exception as exc:
            return ComponentHealth(name="queue", status=UNHEALTHY, detail=str(exc)[:120])

    def _check_model(self) -> ComponentHealth:
        try:
            metadata = self._s3.download_json(f"{self._settings.model_s3_prefix}/latest/metadata.json")
            return ComponentHealth(name="model", status=HEALTHY, detail=f"version={metadata.get('version')}")
        except Exception:
            return ComponentHealth(name="model", status=WARNING, detail="latest model not found in S3")

    def _age_check(self, name: str, latest: datetime | None, max_age: float) -> ComponentHealth:
        if latest is None:
            return ComponentHealth(name=name, status=WARNING, detail="no data yet")
        age = (datetime.now(timezone.utc) - latest).total_seconds()
        if age > max_age:
            return ComponentHealth(name=name, status=WARNING, detail=f"stale ({age:.0f}s old)")
        return ComponentHealth(name=name, status=HEALTHY, detail=f"age={age:.0f}s")

    def _check_prediction(self) -> ComponentHealth:
        try:
            body = self._store.read_json(f"{self._settings.prediction_s3_prefix}/latest.json")
        except Exception as exc:
            return ComponentHealth(name="prediction", status=UNHEALTHY, detail=str(exc)[:120])
        if body is None:
            return ComponentHealth(name="prediction", status=WARNING, detail="no data yet")
        latest = datetime.fromisoformat(body["generated_at"])
        return self._age_check("prediction", latest, self._settings.prediction_interval_seconds * 2)

    def _check_weather(self) -> ComponentHealth:
        try:
            text = self._store.read_text(self._settings.weather_csv_key)
        except Exception as exc:
            return ComponentHealth(name="weather", status=UNHEALTHY, detail=str(exc)[:120])
        if not text:
            return ComponentHealth(name="weather", status=WARNING, detail="no data yet")
        rows = list(csv.DictReader(io.StringIO(text)))
        if not rows:
            return ComponentHealth(name="weather", status=WARNING, detail="csv empty")
        # weather-cron이 매 주기마다 "지금부터" 예보를 새로 써서, 첫 행이 지금과 가까울수록
        # 최신이다 — 오래전에 멈췄다면 첫 행이 이미 지나간 과거 시각으로 남아있게 된다.
        first = datetime.strptime(rows[0]["날짜"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("America/New_York"))
        age = (datetime.now(timezone.utc) - first).total_seconds()
        if age > self._settings.health_weather_max_age_seconds:
            return ComponentHealth(name="weather", status=WARNING, detail=f"stale (first row {age:.0f}s in the past)")
        return ComponentHealth(name="weather", status=HEALTHY, detail=f"first_row_age={age:.0f}s")

    def _check_schedulers(self) -> ComponentHealth:
        stopped = [s.name for s in self._schedulers if not s.is_running]
        failing = [s.name for s in self._schedulers if s.last_error]
        if stopped:
            return ComponentHealth(name="scheduler", status=UNHEALTHY, detail=f"stopped: {stopped}")
        if failing:
            return ComponentHealth(name="scheduler", status=WARNING, detail=f"last_error: {failing}")
        return ComponentHealth(name="scheduler", status=HEALTHY)

    # ---------- 종합 ----------
    def health(self) -> HealthResponse:
        components = [
            self._check_queue(),
            self._check_model(),
            self._check_prediction(),
            self._check_weather(),
            self._check_schedulers(),
        ]
        overall = max((c.status for c in components), key=lambda s: _SEVERITY[s])
        return HealthResponse(status=overall, components=components, checked_at=datetime.now(timezone.utc))

    def ready(self) -> tuple[bool, dict]:
        """Readiness — Queue/Model/Config 초기화 여부."""
        checks = {
            "queue": self._check_queue().status != UNHEALTHY,
            "model": self._check_model().status == HEALTHY,
            "config": bool(self._settings.s3_bucket and self._settings.sqs_queue_name),
        }
        return all(checks.values()), checks
