# Weather Repository — Upsert(동일 zone·시간·타입 중복 저장 방지) + History 조회
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import Weather
from common.models.weather import WeatherRecord


class WeatherRepository(BaseRepository):
    def upsert(self, record: WeatherRecord) -> bool:
        """(zone_id, observed_at, data_type) 기준 Upsert. 신규 삽입이면 True."""
        try:
            stmt = select(Weather).where(
                Weather.zone_id == record.zone_id,
                Weather.observed_at == record.observed_at,
                Weather.data_type == record.data_type,
            )
            existing = self._session.execute(stmt).scalar_one_or_none()
            if existing is not None:
                # 동일 키 재수집 — 최신 값으로 갱신만 (중복 행 생성 금지)
                for field in (
                    "temperature_c", "humidity_pct", "rain_mm", "precipitation_mm",
                    "wind_speed_kmh", "cloud_cover_pct", "weather_code", "visibility_m",
                ):
                    setattr(existing, field, getattr(record, field))
                return False
            self._session.add(Weather(**record.model_dump()))
            self._session.flush()
            return True
        except SQLAlchemyError as exc:
            raise self._wrap("upsert_weather", exc) from exc

    def get_latest(self, zone_id: str | None = None) -> list[Weather]:
        """구역별 최신 1건 (zone_id 지정 시 해당 구역만)."""
        try:
            latest_time = (
                select(Weather.zone_id, func.max(Weather.observed_at).label("max_time"))
                .where(Weather.data_type == "current")
                .group_by(Weather.zone_id)
                .subquery()
            )
            stmt = select(Weather).join(
                latest_time,
                (Weather.zone_id == latest_time.c.zone_id)
                & (Weather.observed_at == latest_time.c.max_time),
            ).where(Weather.data_type == "current")
            if zone_id:
                stmt = stmt.where(Weather.zone_id == zone_id)
            return list(self._session.execute(stmt).scalars())
        except SQLAlchemyError as exc:
            raise self._wrap("select_latest_weather", exc) from exc

    def get_history(
        self, zone_id: str | None, hours: int, limit: int
    ) -> list[Weather]:
        try:
            since = datetime.now(timezone.utc) - timedelta(hours=hours)
            stmt = (
                select(Weather)
                .where(Weather.data_type == "current", Weather.observed_at >= since)
                .order_by(Weather.observed_at.desc())
                .limit(limit)
            )
            if zone_id:
                stmt = stmt.where(Weather.zone_id == zone_id)
            return list(self._session.execute(stmt).scalars())
        except SQLAlchemyError as exc:
            raise self._wrap("select_weather_history", exc) from exc

    def stats(self) -> tuple[int, datetime | None]:
        """(총 레코드 수, 최신 관측 시각) — status API용."""
        try:
            total = self._session.execute(select(func.count(Weather.id))).scalar_one()
            latest = self._session.execute(select(func.max(Weather.observed_at))).scalar_one()
            return total, latest
        except SQLAlchemyError as exc:
            raise self._wrap("select_weather_stats", exc) from exc
