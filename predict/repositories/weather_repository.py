# Predict용 Weather Repository — Forecast 입력(구역별 최신 날씨) 조회 전용
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError

from common.db.base_repository import BaseRepository
from common.db.entities import Weather


class WeatherRepository(BaseRepository):
    def latest_by_zone(self) -> dict[str, dict]:
        """구역별 최신 실측 날씨 → feature dict 매핑."""
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
            )
            result = {}
            for w in self._session.execute(stmt).scalars():
                result[w.zone_id] = {
                    "temperature_c": w.temperature_c,
                    "humidity_pct": w.humidity_pct,
                    "rain_mm": w.rain_mm,
                    "precipitation_mm": w.precipitation_mm,
                    "wind_speed_kmh": w.wind_speed_kmh,
                    "cloud_cover_pct": w.cloud_cover_pct,
                    "weather_code": w.weather_code,
                }
            return result
        except SQLAlchemyError as exc:
            raise self._wrap("select_latest_weather_by_zone", exc) from exc
