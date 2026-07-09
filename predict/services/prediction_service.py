# PredictionService — Forecast Business Logic (Scheduler에는 로직을 두지 않는다)
# Feature 생성 → Model Predict → 후처리 → PredictionDocument → S3 Upload + DB History
import time
from datetime import datetime, timedelta, timezone

from common.aws.s3_adapter import S3Adapter
from common.core.constants import ZONE_COORDINATES
from common.core.exceptions import PredictionError
from common.core.logger import get_logger
from common.core.metrics import (
    PREDICTION_DURATION_SECONDS,
    PREDICTION_FAILURE_TOTAL,
    PREDICTION_LATEST_VALUE,
    PREDICTION_TOTAL,
    metrics,
)
from common.db.database import Database
from common.models.prediction import PredictionDocument, PredictionItem

# 학습·서빙 공유 피처 모듈 (ml/features.py — train-serve skew 방지)
from features import build_feature_row, to_dataframe

from config import PredictSettings
from ml_runtime.model_loader import ModelLoader
from repositories.call_repository import CallRepository
from repositories.prediction_repository import PredictionRepository
from repositories.weather_repository import WeatherRepository

logger = get_logger("prediction_service")


class PredictionService:
    def __init__(
        self,
        model_loader: ModelLoader,
        s3: S3Adapter,
        database: Database,
        settings: PredictSettings,
    ):
        self._model_loader = model_loader
        self._s3 = s3
        self._db = database
        self._settings = settings

    # ---------- Retry 공통 (Model Download / Predict / Upload) ----------
    def _with_retry(self, name: str, fn):
        last_exc: Exception | None = None
        for attempt in range(1, self._settings.forecast_retry_count + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    f"{name} retry {attempt}/{self._settings.forecast_retry_count}: {exc}",
                    extra={"event": "forecast_retry", "count": attempt, "detail": {"step": name}},
                )
                if attempt < self._settings.forecast_retry_count:
                    time.sleep(self._settings.forecast_retry_backoff_seconds * attempt)
        raise last_exc

    # ---------- Forecast 1회 실행 ----------
    def run_forecast(self) -> PredictionDocument:
        started = time.monotonic()
        logger.info("prediction started", extra={"event": "prediction_started"})
        try:
            document = self._run(started)
            metrics.increment(PREDICTION_TOTAL)
            return document
        except Exception as exc:
            metrics.increment(PREDICTION_FAILURE_TOTAL)
            logger.exception("prediction failed", extra={"event": "prediction_failed"})
            raise PredictionError(f"forecast run failed: {exc}") from exc

    def _run(self, started: float) -> PredictionDocument:
        settings = self._settings
        # 1) Model Load (Retry) — 항상 latest 버전
        booster, metadata = self._with_retry("model_download", self._model_loader.load_latest)
        model_version = metadata.get("version", "unknown")

        # 2) 입력 데이터 로드 (Weather + Call History)
        with self._db.session_scope() as session:
            weather_by_zone = WeatherRepository(session).latest_by_zone()
            recent_by_zone = CallRepository(session).recent_calls_by_zone()
        logger.info(
            "weather loaded", extra={"event": "weather_loaded", "count": len(weather_by_zone)}
        )
        logger.info(
            "call history loaded", extra={"event": "call_history_loaded", "count": len(recent_by_zone)}
        )

        # 3) Feature Engineering (공유 모듈) — 구역 × horizon 시간창
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=settings.prediction_window_minutes)
        zones = sorted(ZONE_COORDINATES)
        keys: list[tuple[str, datetime]] = []
        rows: list[dict] = []
        for step in range(settings.prediction_horizon_steps):
            target_time = now + window * step
            for zone in zones:
                keys.append((zone, target_time))
                rows.append(
                    build_feature_row(
                        zone, target_time, weather_by_zone.get(zone), recent_by_zone.get(zone)
                    )
                )
        features = to_dataframe(rows)

        # 4) LightGBM Predict (Retry) + 후처리 (음수 클립·반올림·confidence)
        raw = self._with_retry("model_predict", lambda: booster.predict(features))
        cv_mae = float(metadata.get("cv_mae") or 0.0)
        items = []
        for (zone, target_time), value in zip(keys, raw):
            demand = round(max(0.0, float(value)), 2)
            confidence = round(max(0.0, min(1.0, 1.0 - cv_mae / (demand + cv_mae + 1e-6))), 2)
            items.append(
                PredictionItem(
                    zone_id=zone,
                    target_time=target_time,
                    predicted_demand=demand,
                    confidence=confidence,
                )
            )

        first_window_total = round(
            sum(i.predicted_demand for i in items if i.target_time == now), 2
        )
        document = PredictionDocument(
            generated_at=now,
            model_version=model_version,
            prediction_window_minutes=settings.prediction_window_minutes,
            horizon_steps=settings.prediction_horizon_steps,
            total_predicted_demand=first_window_total,
            predictions=items,
        )
        metrics.observe(PREDICTION_LATEST_VALUE, first_window_total)
        logger.info(
            f"prediction completed (total={first_window_total}, zones={len(zones)})",
            extra={
                "event": "prediction_completed",
                "detail": {"model_version": model_version, "total": first_window_total},
            },
        )

        # 5) S3 Upload (Retry) — latest + 타임스탬프 이력
        prefix = settings.prediction_s3_prefix
        body = document.model_dump(mode="json")
        self._with_retry("s3_upload", lambda: self._s3.upload_json(f"{prefix}/latest.json", body))
        if settings.prediction_keep_history_in_s3:
            ts_key = f"{prefix}/history/{now.strftime('%Y%m%d-%H%M%S')}.json"
            self._with_retry("s3_upload_history", lambda: self._s3.upload_json(ts_key, body))
        logger.info(
            "prediction uploaded",
            extra={"event": "prediction_uploaded", "detail": {"key": f"{prefix}/latest.json"}},
        )

        # 6) Prediction History DB 저장 (Dashboard용)
        with self._db.session_scope() as session:
            saved = PredictionRepository(session).save_document(document)
        metrics.observe(PREDICTION_DURATION_SECONDS, time.monotonic() - started)
        logger.info(
            f"prediction history saved ({saved} rows)",
            extra={"event": "prediction_saved", "count": saved},
        )
        return document
