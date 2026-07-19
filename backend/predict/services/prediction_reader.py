# Prediction Reader — 최신 예측을 읽고 Schema Validation을 수행한다.
# 추상 인터페이스라 구현체 교체 가능 (DI 지점: dependencies.py).
from abc import ABC, abstractmethod

from pydantic import ValidationError

from common.core.logger import get_logger
from common.core.store import FileStore
from common.db.database import Database
from common.models.prediction import PredictionDocument, PredictionItem

from repositories.prediction_repository import PredictionRepository

logger = get_logger("prediction_reader")


class PredictionReader(ABC):
    @abstractmethod
    def read_latest(self) -> PredictionDocument | None:
        """검증된 최신 Prediction. 없거나 스키마가 비정상이면 None (→ Scaling 수행 안 함)."""


class FilePredictionReader(PredictionReader):
    def __init__(self, store: FileStore, prediction_prefix: str):
        self._store = store
        self._key = f"{prediction_prefix}/latest.json"

    def read_latest(self) -> PredictionDocument | None:
        body = self._store.read_json(self._key)
        if body is None:
            logger.warning(
                "prediction.json not available",
                extra={"event": "prediction_missing", "detail": {"key": self._key}},
            )
            return None
        try:
            document = PredictionDocument.model_validate(body)  # 필수값 Schema Validation
        except ValidationError as exc:
            logger.error(
                f"prediction.json schema invalid: {exc.errors()[:3]}",
                extra={"event": "prediction_invalid", "detail": {"key": self._key}},
            )
            return None
        logger.info(
            # 07-13 네이밍 규약에 따른 변수명 및 코드 수정 중 1. 예측 지표 이름 불일치
            f"prediction loaded (total={document.predicted_taxi_demand})",
            extra={
                "event": "prediction_loaded",
                "detail": {
                    "generated_at": document.generated_at.isoformat(),
                    "model_version": document.model_version,
                },
            },
        )
        return document


class DbPredictionReader(PredictionReader):
    """RDS `Prediction` 테이블에서 최신 배치를 읽는다 (07-15 §4-5 확정 —
    ScalerService 스케일링 판단 + 대시보드 조회 공용 소스)."""

    def __init__(self, database: Database, window_minutes: int):
        self._db = database
        self._window_minutes = window_minutes

    def read_latest(self) -> PredictionDocument | None:
        with self._db.session_scope() as session:
            repo = PredictionRepository(session)
            generated_at = repo.latest_generated_at()
            if generated_at is None:
                logger.warning("no prediction rows in RDS", extra={"event": "prediction_missing"})
                return None
            rows = repo.get_batch(generated_at)
            if not rows:
                return None
            items = [
                PredictionItem(
                    target_time=row.target_time,
                    predicted_demand=row.predicted_demand,
                    confidence=row.confidence,
                    temperature=row.temperature,
                    humidity=row.humidity,
                    is_raining=bool(row.is_raining) if row.is_raining is not None else None,
                )
                for row in rows
            ]
            document = PredictionDocument(
                generated_at=generated_at,
                model_version=rows[0].model_version,
                prediction_window_minutes=rows[0].prediction_window_minutes or self._window_minutes,
                horizon_steps=len(items),
                predicted_taxi_demand=items[0].predicted_demand,
                predictions=items,
            )
        logger.info(
            f"prediction loaded from RDS (total={document.predicted_taxi_demand})",
            extra={
                "event": "prediction_loaded",
                "detail": {
                    "generated_at": document.generated_at.isoformat(),
                    "model_version": document.model_version,
                },
            },
        )
        return document
