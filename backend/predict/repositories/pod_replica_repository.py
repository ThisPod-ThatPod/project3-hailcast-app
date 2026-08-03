# Pod Replica History Repository — 시간대별 예측/실제 파드 수 백업 저장·조회
# [미사용, 2026-07-13] DB(J3) 대신 FileStore(dashboard/pod-history.json)로 재설계되면서
# 코드 어디서도 안 부름 — RDS 도입 시 재사용 가능하게 삭제하지 않고 남겨둠.
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import PodReplicaHistory


class PodReplicaRepository(BaseRepository):
    def upsert(
        self,
        bucket_time: datetime,
        *,
        predicted_replicas: int | None = None,
        actual_replicas: int | None = None,
        model_version: str | None = None,
    ) -> None:
        """(bucket_time) 기준 Upsert. predicted/actual은 None이 아닌 값만 갱신한다."""
        try:
            stmt = select(PodReplicaHistory).where(PodReplicaHistory.bucket_time == bucket_time)
            existing = self._session.execute(stmt).scalar_one_or_none()
            if existing is not None:
                if predicted_replicas is not None:
                    existing.predicted_replicas = predicted_replicas
                if actual_replicas is not None:
                    existing.actual_replicas = actual_replicas
                if model_version is not None:
                    existing.model_version = model_version
            else:
                self._session.add(
                    PodReplicaHistory(
                        bucket_time=bucket_time,
                        predicted_replicas=predicted_replicas,
                        actual_replicas=actual_replicas,
                        model_version=model_version,
                    )
                )
            self._session.flush()
        except SQLAlchemyError as exc:
            raise self._wrap("upsert_pod_replica_history", exc) from exc

    def get_range(self, start: datetime, end: datetime) -> list[PodReplicaHistory]:
        """[start, end) 구간의 시간순 이력 (과거 그래프 구간 조회용)."""
        try:
            stmt = (
                select(PodReplicaHistory)
                .where(PodReplicaHistory.bucket_time >= start, PodReplicaHistory.bucket_time < end)
                .order_by(PodReplicaHistory.bucket_time)
            )
            return list(self._session.execute(stmt).scalars())
        except SQLAlchemyError as exc:
            raise self._wrap("select_pod_replica_history", exc) from exc
