# PredictionService — Forecast Business Logic (Scheduler에는 로직을 두지 않는다)
# weather-cron이 FileStore에 저장한 NYC 30시간 예보 CSV(30분 간격) → 시간 버킷별로
# 묶어서 그 시간의 :00/:30 두 시나리오를 각각 예측 → 더 큰(악조건) 쪽을 그 시간의
# 대표값으로 채택 → PredictionDocument로 JSON+CSV 저장.
#
# zone 없음 — 학습 데이터(ml/train.py, 뉴욕 택시+날씨)와 같은 분포를 맞추기 위해 실제 서비스
# 지역(서울) 대신 뉴욕 날씨를 그대로 쓰는 글로벌 수요 예측 하나만 만든다 (실배포 없는 데모 전제).
import csv
import io
import time
from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from common.core.exceptions import PredictionError
from common.core.logger import get_logger
from common.core.store import FileStore
from common.db.database import Database
from common.models.prediction import PredictionDocument, PredictionItem

# 학습·서빙 공유 피처 모듈 (ml/features.py — train-serve skew 방지)
from features import build_features, to_model_input

from config import PredictSettings
from ml_runtime.model_loader import ModelLoader
from repositories.prediction_repository import PredictionRepository

logger = get_logger("prediction_service")

# weather-cron이 이 timezone(America/New_York)으로 CSV를 만든다 — 시간 버킷 매칭도
# 같은 timezone 기준이어야 "지금 다음 4시간"이 CSV 행과 정확히 맞물린다.
NYC_TZ = ZoneInfo("America/New_York")


def _weekday_sunday_zero(dt: datetime) -> int:
    # weather_service.py, ml/features.py, ml/preprocess.py와 동일 공식 (일=0 ... 토=6).
    return (dt.weekday() + 1) % 7


class PredictionService:
    def __init__(
        self, model_loader: ModelLoader, store: FileStore, database: Database, settings: PredictSettings
    ):
        self._model_loader = model_loader
        self._store = store
        self._db = database
        self._settings = settings

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

    def run_forecast(self) -> PredictionDocument:
        started = time.monotonic()
        logger.info("prediction started", extra={"event": "prediction_started"})
        try:
            document = self._run(started)
            return document
        except Exception as exc:
            logger.exception("prediction failed", extra={"event": "prediction_failed"})
            raise PredictionError(f"forecast run failed: {exc}") from exc

    def _run(self, started: float) -> PredictionDocument:
        settings = self._settings
        model, metadata = self._with_retry("model_download", self._model_loader.load_latest)
        model_version = metadata.get("version", "unknown")

        rows = self._load_weather_rows()
        if not rows:
            raise PredictionError(
                f"weather forecast CSV empty/missing at '{settings.weather_csv_key}' — "
                "weather-cron이 먼저 돌아야 한다"
            )
        buckets = self._group_by_hour(rows)

        now_local = datetime.now(NYC_TZ).replace(minute=0, second=0, microsecond=0)
        target_hours = sorted(h for h in buckets if h >= now_local)[: settings.prediction_horizon_hours]
        if not target_hours:
            raise PredictionError("weather forecast CSV has no rows at/after current hour")

        items: list[PredictionItem] = []
        for hour_start in target_hours:
            best_demand = 0.0
            best_row = buckets[hour_start][0]
            for row in buckets[hour_start]:
                features = build_features(hour_start, row["temperature"], row["humidity"], row["is_raining"])
                model_input = to_model_input(features)
                raw = self._with_retry("model_predict", lambda mi=model_input: model.predict(mi)[0])
                if float(raw) >= best_demand:
                    best_demand = float(raw)
                    best_row = row
            items.append(
                PredictionItem(
                    target_time=hour_start.astimezone(timezone.utc),
                    predicted_demand=round(max(0.0, best_demand), 2),
                    temperature=best_row["temperature"],
                    humidity=best_row["humidity"],
                    is_raining=best_row["is_raining"],
                )
            )

        generated_at = datetime.now(timezone.utc)
        first_total = items[0].predicted_demand if items else 0.0
        document = PredictionDocument(
            generated_at=generated_at,
            model_version=model_version,
            prediction_window_minutes=settings.prediction_window_minutes,
            horizon_steps=len(items),
            # 07-13 네이밍 규약에 따른 변수명 및 코드 수정 중 1. 예측 지표 이름 불일치
            # total_predicted_demand=first_total,
            predicted_taxi_demand=first_total,
            predictions=items,
        )
        logger.info(
            f"prediction completed (hours={len(items)}, first={first_total})",
            extra={
                "event": "prediction_completed",
                "detail": {"model_version": model_version, "hours": len(items), "first_total": first_total},
            },
        )

        self._save(document)
        logger.info(
            "prediction saved",
            extra={"event": "prediction_saved", "detail": {"key": f"{settings.prediction_s3_prefix}/latest.json"}},
        )
        return document

    def _load_weather_rows(self) -> list[dict]:
        text = self._store.read_text(self._settings.weather_csv_key)
        if not text:
            return []
        rows = []
        for r in csv.DictReader(io.StringIO(text)):
            dt = datetime.strptime(r["날짜"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=NYC_TZ)
            rows.append(
                {
                    "time": dt,
                    "temperature": float(r["온도"]),
                    "humidity": float(r["습도"]),
                    "is_raining": bool(int(r["강수유무"])),
                }
            )
        return rows

    @staticmethod
    def _group_by_hour(rows: list[dict]) -> dict[datetime, list[dict]]:
        buckets: dict[datetime, list[dict]] = defaultdict(list)
        for row in rows:
            hour_start = row["time"].replace(minute=0, second=0, microsecond=0)
            buckets[hour_start].append(row)
        return buckets

    def _save(self, document: PredictionDocument) -> None:
        prefix = self._settings.prediction_s3_prefix
        body = document.model_dump(mode="json")
        self._with_retry("store_write", lambda: self._store.write_json(f"{prefix}/latest.json", body))
        if self._settings.prediction_keep_history_in_s3:
            ts_key = f"{prefix}/history/{document.generated_at.strftime('%Y%m%d-%H%M%S')}.json"
            self._with_retry("store_write_history", lambda: self._store.write_json(ts_key, body))
        self._save_csv(document, prefix)
        self._with_retry("db_write", lambda: self._save_to_db(document))

    def _save_to_db(self, document: PredictionDocument) -> None:
        # 07-15 §4-5 확정 — RDS가 대시보드 조회 + ScalerService 스케일링 판단 소스 겸용.
        # S3(위)는 그대로 유지: GET /prediction/latest·health check가 아직 S3를 직접 읽는다.
        with self._db.session_scope() as session:
            PredictionRepository(session).save_document(document)

    def _save_csv(self, document: PredictionDocument, prefix: str) -> None:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=["날짜", "요일", "시간", "예측수요"])
        writer.writeheader()
        for item in document.predictions:
            local = item.target_time.astimezone(NYC_TZ)
            writer.writerow(
                {
                    "날짜": local.strftime("%Y-%m-%d"),
                    "요일": _weekday_sunday_zero(local),
                    "시간": local.hour,
                    "예측수요": item.predicted_demand,
                }
            )
        self._store.write_text(f"{prefix}/latest.csv", buf.getvalue())
