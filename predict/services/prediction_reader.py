# Prediction Reader — S3의 prediction.json을 읽고 Schema Validation을 수행한다.
# 추상 인터페이스라 테스트/Simulator 연동 시 Mock Reader로 교체 가능하다 (DI 지점: dependencies.py).
from abc import ABC, abstractmethod

from pydantic import ValidationError

from common.aws.s3_adapter import S3Adapter
from common.core.exceptions import AwsError
from common.core.logger import get_logger
from common.models.prediction import PredictionDocument

logger = get_logger("prediction_reader")


class PredictionReader(ABC):
    @abstractmethod
    def read_latest(self) -> PredictionDocument | None:
        """검증된 최신 Prediction. 없거나 스키마가 비정상이면 None (→ Scaling 수행 안 함)."""


class S3PredictionReader(PredictionReader):
    def __init__(self, s3: S3Adapter, prediction_prefix: str):
        self._s3 = s3
        self._key = f"{prediction_prefix}/latest.json"

    def read_latest(self) -> PredictionDocument | None:
        try:
            body = self._s3.download_json(self._key)
        except AwsError as exc:
            logger.warning(
                f"prediction.json not available: {exc.message}",
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
            f"prediction loaded (total={document.total_predicted_demand})",
            extra={
                "event": "prediction_loaded",
                "detail": {
                    "generated_at": document.generated_at.isoformat(),
                    "model_version": document.model_version,
                },
            },
        )
        return document
