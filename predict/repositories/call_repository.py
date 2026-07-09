# Predict용 Call Repository — 최근 수요(Call History) Feature 조회 전용
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import Call


class CallRepository(BaseRepository):
    def _count_since(self, since: datetime) -> dict[str, int]:
        stmt = (
            select(Call.zone_id, func.count(Call.id))
            .where(Call.requested_at >= since, Call.zone_id.isnot(None))
            .group_by(Call.zone_id)
        )
        return {zone: count for zone, count in self._session.execute(stmt).all()}

    def recent_calls_by_zone(self) -> dict[str, dict]:
        """구역별 {recent_calls_1h, recent_calls_3h, recent_calls_24h} feature."""
        try:
            now = datetime.now(timezone.utc)
            h1 = self._count_since(now - timedelta(hours=1))
            h3 = self._count_since(now - timedelta(hours=3))
            h24 = self._count_since(now - timedelta(hours=24))
            zones = set(h1) | set(h3) | set(h24)
            return {
                zone: {
                    "recent_calls_1h": h1.get(zone, 0),
                    "recent_calls_3h": h3.get(zone, 0),
                    "recent_calls_24h": h24.get(zone, 0),
                }
                for zone in zones
            }
        except SQLAlchemyError as exc:
            raise self._wrap("select_recent_calls", exc) from exc
