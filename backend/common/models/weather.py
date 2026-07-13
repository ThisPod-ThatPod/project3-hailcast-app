# Weather DTO — 조회 API 응답에 사용
from datetime import datetime

from pydantic import BaseModel


class WeatherStatusResponse(BaseModel):
    """GET /weather/status — Dashboard/트러블슈팅용 수집 상태."""

    scheduler_running: bool
    interval_seconds: float
    csv_key: str
    last_saved_rows: int | None = None
    last_run_at: datetime | None = None
    last_success_at: datetime | None = None
    last_error: str | None = None
    run_count: int
    failure_count: int
