# Prediction Repository — 예측 History 저장/조회
# [미사용, 2026-07-13] DB(J3) 대신 FileStore(predictions/latest.json + history/)로
# 재설계되면서 코드 어디서도 안 부름 — RDS 도입 시 재사용 가능하게 삭제하지 않고 남겨둠.
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import Prediction
from common.models.prediction import PredictionDocument


class PredictionRepository(BaseRepository):
    def save_document(self, document: PredictionDocument) -> int:
        try:
            for item in document.predictions:
                self._session.add(
                    Prediction(
                        target_time=item.target_time,
                        predicted_demand=item.predicted_demand,
                        confidence=item.confidence,
                        prediction_window_minutes=document.prediction_window_minutes,
                        model_version=document.model_version,
                        generated_at=document.generated_at,
                    )
                )
            self._session.flush()
            return len(document.predictions)
        except SQLAlchemyError as exc:
            raise self._wrap("insert_predictions", exc) from exc

    def latest_generated_at(self) -> datetime | None:
        try:
            return self._session.execute(select(func.max(Prediction.generated_at))).scalar_one()
        except SQLAlchemyError as exc:
            raise self._wrap("select_latest_generated_at", exc) from exc

    def get_batch(self, generated_at: datetime) -> list[Prediction]:
        try:
            stmt = (
                select(Prediction)
                .where(Prediction.generated_at == generated_at)
                .order_by(Prediction.target_time)
            )
            return list(self._session.execute(stmt).scalars())
        except SQLAlchemyError as exc:
            raise self._wrap("select_prediction_batch", exc) from exc

    def get_history(self, limit: int) -> list[Prediction]:
        try:
            stmt = select(Prediction).order_by(Prediction.generated_at.desc(), Prediction.target_time).limit(limit)
            return list(self._session.execute(stmt).scalars())
        except SQLAlchemyError as exc:
            raise self._wrap("select_prediction_history", exc) from exc

    def stats(self) -> tuple[int, str | None]:
        """(총 저장 건수, 최신 model_version)"""
        try:
            total = self._session.execute(select(func.count(Prediction.id))).scalar_one()
            version = self._session.execute(
                select(Prediction.model_version).order_by(Prediction.generated_at.desc()).limit(1)
            ).scalar_one_or_none()
            return total, version
        except SQLAlchemyError as exc:
            raise self._wrap("select_prediction_stats", exc) from exc
