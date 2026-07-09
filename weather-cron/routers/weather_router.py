# Weather Router — Dashboard/Frontend 조회용. 위임만 수행.
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from common.models.weather import WeatherRecord, WeatherStatusResponse

from config import get_settings
from dependencies import get_db_session, get_weather_scheduler
from repositories.weather_repository import WeatherRepository

router = APIRouter(prefix="/weather", tags=["weather"])


def _to_record(entity) -> WeatherRecord:
    return WeatherRecord.model_validate(entity, from_attributes=True)


@router.get("/latest", response_model=list[WeatherRecord])
def latest(
    zone_id: str | None = Query(default=None),
    session: Session = Depends(get_db_session),
) -> list[WeatherRecord]:
    return [_to_record(w) for w in WeatherRepository(session).get_latest(zone_id)]


@router.get("/history", response_model=list[WeatherRecord])
def history(
    zone_id: str | None = Query(default=None),
    hours: int = Query(default=None, ge=1, le=24 * 30),
    limit: int = Query(default=100, ge=1),
    session: Session = Depends(get_db_session),
) -> list[WeatherRecord]:
    settings = get_settings()
    return [
        _to_record(w)
        for w in WeatherRepository(session).get_history(
            zone_id,
            hours=hours or settings.weather_history_default_hours,
            limit=min(limit, settings.weather_history_max_limit),
        )
    ]


@router.get("/status", response_model=WeatherStatusResponse)
def status(session: Session = Depends(get_db_session)) -> WeatherStatusResponse:
    scheduler = get_weather_scheduler()
    total, latest_observed = WeatherRepository(session).stats()
    return WeatherStatusResponse(
        scheduler_running=scheduler.is_running,
        interval_seconds=scheduler.interval_seconds,
        zones=len(get_settings().locations()),
        total_records=total,
        latest_observed_at=latest_observed,
        last_run_at=scheduler.last_run_at,
        last_success_at=scheduler.last_success_at,
        last_error=scheduler.last_error,
        run_count=scheduler.run_count,
        failure_count=scheduler.failure_count,
    )
