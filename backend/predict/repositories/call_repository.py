# Predict용 Call Repository — Dashboard 트래픽 그래프 조회 전용
# [미사용, 2026-07-16] traffic/dashboard 프리픽스는 D-1 결정으로 S3 유지 확정 —
# 콜 쓰기/단건조회만 RDS로 갔다(common/db/call_repository.py). 이 파일은 여전히 미사용.
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import Call


class CallRepository(BaseRepository):
    def traffic_history(self, since: datetime, bucket_seconds: int) -> dict[datetime, int]:
        """since 이후 call-api 수신 요청을 bucket_seconds 단위로 집계 (Dashboard 트래픽 그래프).

        Call.enqueued_at(call-api 접수 시각) 기준 — call-api/worker 파드 수·트래픽 출처와
        무관하게 DB 하나로 전체 합산된다. 버킷이 빈 구간은 결과에 포함되지 않는다(호출부에서 0 채움).
        """
        try:
            stmt = select(Call.enqueued_at).where(Call.enqueued_at >= since)
            timestamps = self._session.execute(stmt).scalars().all()
        except SQLAlchemyError as exc:
            raise self._wrap("select_traffic_history", exc) from exc

        buckets: dict[datetime, int] = {}
        for ts in timestamps:
            epoch = ts.timestamp()
            bucket_epoch = epoch - (epoch % bucket_seconds)
            bucket = datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)
            buckets[bucket] = buckets.get(bucket, 0) + 1
        return buckets
