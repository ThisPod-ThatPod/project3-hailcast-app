# Scaling Repository — 스케일링 이력 저장/조회 (Dashboard + Cooldown 기준 시각)
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import ScalingEvent


class ScalingRepository(BaseRepository):
    def save_event(
        self,
        *,
        predicted_demand: float,
        old_replica: int,
        new_replica: int,
        action: str,
        reason: str,
        model_version: str | None,
    ) -> None:
        try:
            self._session.add(
                ScalingEvent(
                    predicted_demand=predicted_demand,
                    old_replica=old_replica,
                    new_replica=new_replica,
                    action=action,
                    reason=reason[:256],
                    model_version=model_version,
                )
            )
            self._session.flush()
        except SQLAlchemyError as exc:
            raise self._wrap("insert_scaling_event", exc) from exc

    def get_history(self, limit: int) -> list[ScalingEvent]:
        try:
            stmt = select(ScalingEvent).order_by(ScalingEvent.created_at.desc()).limit(limit)
            return list(self._session.execute(stmt).scalars())
        except SQLAlchemyError as exc:
            raise self._wrap("select_scaling_history", exc) from exc

    def last_event_time(self) -> datetime | None:
        """Cooldown 판정 기준 — 마지막 replica 변경 시각 (재시작에도 유지되도록 DB 사용)."""
        try:
            stmt = select(ScalingEvent.created_at).order_by(ScalingEvent.created_at.desc()).limit(1)
            return self._session.execute(stmt).scalar_one_or_none()
        except SQLAlchemyError as exc:
            raise self._wrap("select_last_scaling_time", exc) from exc
