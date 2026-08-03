# Weather Router — 수집 상태 조회용 (트러블슈팅). 위임만 수행.
# 실제 예보 데이터는 predict가 FileStore로 CSV를 직접 읽는다 — 여기서 HTTP로 안 내려준다.
from fastapi import APIRouter

from common.models.weather import WeatherStatusResponse

from config import get_settings
from dependencies import get_weather_scheduler, get_weather_service

router = APIRouter(prefix="/weather", tags=["weather"])


@router.get("/status", response_model=WeatherStatusResponse)
def status() -> WeatherStatusResponse:
    scheduler = get_weather_scheduler()
    return WeatherStatusResponse(
        scheduler_running=scheduler.is_running,
        interval_seconds=scheduler.interval_seconds,
        csv_key=get_settings().weather_csv_key,
        last_saved_rows=get_weather_service().last_row_count,
        last_run_at=scheduler.last_run_at,
        last_success_at=scheduler.last_success_at,
        last_error=scheduler.last_error,
        run_count=scheduler.run_count,
        failure_count=scheduler.failure_count,
    )
