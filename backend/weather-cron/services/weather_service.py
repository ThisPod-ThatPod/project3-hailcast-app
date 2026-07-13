# WeatherService — 수집 Business Logic: Adapter 호출(Retry) → CSV 매핑 → FileStore 저장
import asyncio
import csv
import io
from datetime import datetime

from common.core.constants import NYC_LATITUDE, NYC_LONGITUDE
from common.core.exceptions import ExternalApiError
from common.core.logger import get_logger
from common.core.store import FileStore

from adapters.weather_adapter import WeatherAdapter
from config import WeatherSettings

logger = get_logger("weather_service")

# ml/preprocess.py가 만드는 학습 데이터, ml/features.py::dataframe_to_features가 읽는
# 컬럼과 이름·순서가 정확히 같아야 한다 (승객수 컬럼만 없음 — 그건 학습 데이터 전용).
_CSV_FIELDS = ["날짜", "요일", "온도", "습도", "강수유무"]


def _weekday_sunday_zero(dt: datetime) -> int:
    # ml/features.py::weekday_sunday_zero, ml/preprocess.py::weekday_sunday_zero와
    # 반드시 같은 공식이어야 한다 (일=0, 월=1, ... 토=6). 학습된 모델의 인코딩이 이
    # 값에 고정돼 있어서 바뀌면 예측이 어긋난다.
    return (dt.weekday() + 1) % 7


class WeatherService:
    def __init__(self, adapter: WeatherAdapter, store: FileStore, settings: WeatherSettings):
        self._adapter = adapter
        self._store = store
        self._settings = settings
        self.last_row_count: int | None = None  # /weather/status 조회용

    async def collect(self) -> int:
        """NYC 향후 weather_forecast_hours시간 예보를 받아 CSV로 저장. 반환값=저장된 행 수.

        실패해도 예외를 올리지 않는다 — Scheduler(IntervalScheduler)가 어차피 다음
        주기까지 정상 대기하므로, 여기서는 로그만 남기고 0을 반환해 그 사실을 알린다.
        """
        try:
            points = await self._fetch_with_retry()
        except ExternalApiError as exc:
            logger.error(
                f"weather collection failed: {exc}",
                extra={"event": "weather_failure", "detail": {"message": exc.message}},
            )
            self.last_row_count = 0
            return 0

        rows = [self._to_row(point) for point in points]

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
        self._store.write_text(self._settings.weather_csv_key, buf.getvalue())

        logger.info(
            f"weather forecast saved ({len(rows)} rows)",
            extra={"event": "weather_saved", "detail": {"rows": len(rows), "key": self._settings.weather_csv_key}},
        )
        self.last_row_count = len(rows)
        return len(rows)

    @staticmethod
    def _to_row(point: dict) -> dict:
        dt = datetime.fromisoformat(point["time"])
        temperature = point["temperature"]
        humidity = point["humidity"]
        return {
            "날짜": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "요일": _weekday_sunday_zero(dt),
            "온도": round(temperature, 1) if temperature is not None else "",
            "습도": round(humidity) if humidity is not None else "",
            "강수유무": int(bool(point["is_raining"])),
        }

    async def _fetch_with_retry(self) -> list[dict]:
        last_exc: ExternalApiError | None = None
        for attempt in range(1, self._settings.weather_retry_count + 1):
            try:
                return await self._adapter.fetch_forecast(
                    NYC_LATITUDE, NYC_LONGITUDE, self._settings.weather_forecast_hours
                )
            except ExternalApiError as exc:
                last_exc = exc
                logger.warning(
                    f"weather request retry {attempt}/{self._settings.weather_retry_count}: {exc.message}",
                    extra={"event": "weather_retry", "count": attempt},
                )
                if attempt < self._settings.weather_retry_count:
                    await asyncio.sleep(self._settings.weather_retry_backoff_seconds * attempt)
        raise last_exc  # Retry 소진 — 호출부(collect)가 기록하고 다음 주기까지 대기
