# Prediction Reader — FileStore의 prediction.json을 읽고 Schema Validation을 수행한다.
# 추상 인터페이스라 테스트/Simulator 연동 시 Mock Reader로 교체 가능하다 (DI 지점: dependencies.py).
from abc import ABC, abstractmethod

from pydantic import ValidationError

from common.core.logger import get_logger
from common.core.store import FileStore
from common.models.prediction import PredictionDocument

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
            # f"prediction loaded (total={document.total_predicted_demand})",
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
