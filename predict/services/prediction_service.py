# PredictionService — Forecast Business Logic (Scheduler에는 로직을 두지 않는다)
# 뉴욕 날씨(Open-Meteo) → Feature 생성 → Model Predict → PredictionDocument → S3 Upload + DB History
#
# zone 없음 — 학습 데이터(ml/train.py, 뉴욕 택시+날씨)와 같은 분포를 맞추기 위해 실제 서비스
# 지역(서울) 대신 뉴욕 날씨를 그대로 쓰는 글로벌 수요 예측 하나만 만든다 (실배포 없는 데모 전제).
import time
from datetime import datetime, timedelta, timezone

from common.aws.s3_adapter import S3Adapter
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
from features import build_features, to_model_input

from adapters.nyc_weather_adapter import NycWeatherAdapter
from config import PredictSettings
from ml_runtime.model_loader import ModelLoader
from repositories.prediction_repository import PredictionRepository

logger = get_logger("prediction_service")


class PredictionService:
    def __init__(
        self,
        model_loader: ModelLoader,
        weather: NycWeatherAdapter,
        s3: S3Adapter,
        database: Database,
        settings: PredictSettings,
    ):
        self._model_loader = model_loader
        self._weather = weather
        self._s3 = s3
        self._db = database
        self._settings = settings

    # ---------- Retry 공통 (Model Download / Weather Fetch / Predict / Upload) ----------
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
        model, metadata = self._with_retry("model_download", self._model_loader.load_latest)
        model_version = metadata.get("version", "unknown")

        # 2) 뉴욕 현재 날씨 (Retry)
        weather = self._with_retry("weather_fetch", self._weather.fetch_current)
        logger.info("weather loaded", extra={"event": "weather_loaded", "detail": weather})

        # 3) Feature Engineering (공유 모듈) — horizon step마다 1건 (zone 없음)
        now = datetime.now(timezone.utc)
        window = timedelta(minutes=settings.prediction_window_minutes)
        items: list[PredictionItem] = []
        for step in range(settings.prediction_horizon_steps):
            target_time = now + window * step
            features = build_features(
                target_time, weather["temperature"], weather["humidity"], weather["is_raining"]
            )
            model_input = to_model_input(features)

            # 4) LightGBM Predict (Retry) + 후처리 (음수 클립·반올림)
            raw = self._with_retry("model_predict", lambda mi=model_input: model.predict(mi)[0])
            demand = round(max(0.0, float(raw)), 2)
            items.append(PredictionItem(target_time=target_time, predicted_demand=demand))

        first_window_total = items[0].predicted_demand if items else 0.0
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
            f"prediction completed (total={first_window_total})",
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
