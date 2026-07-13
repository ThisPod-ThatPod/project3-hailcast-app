# Open-Meteo 구현체 — https://open-meteo.com (API 키 불필요)
# minutely_15(15분 단위) 예보를 받아 30분 간격(:00, :30)만 골라 쓴다 — hourly 블록은
# 시간당 1개뿐이라 "1시엔 안 오던 비가 1시반엔 온다" 같은 시간 내 변화를 못 잡는다.
import httpx

from common.core.exceptions import ExternalApiError
from common.core.logger import get_logger

from adapters.weather_adapter import WeatherAdapter

logger = get_logger("open_meteo")

_MINUTELY_VARS = ["temperature_2m", "relative_humidity_2m", "precipitation"]


class OpenMeteoAdapter(WeatherAdapter):
    provider = "open-meteo"

    def __init__(self, base_url: str, timeout_seconds: float):
        self._base_url = base_url
        self._timeout = timeout_seconds

    async def fetch_forecast(self, latitude: float, longitude: float, hours: int) -> list[dict]:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "minutely_15": ",".join(_MINUTELY_VARS),
            "forecast_minutely_15": hours * 4,  # 15분 단위 포인트 수
            # ml/preprocess.py와 같은 timezone — hour 파싱이 학습 데이터와 어긋나지 않게 한다.
            "timezone": "America/New_York",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                logger.info(
                    "weather forecast request",
                    extra={"event": "weather_request", "detail": {"lat": latitude, "lon": longitude, "hours": hours}},
                )
                response = await client.get(self._base_url, params=params)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise ExternalApiError(
                f"open-meteo request failed: {exc}",
                provider=self.provider,
                detail={"lat": latitude, "lon": longitude},
            ) from exc

        block = payload.get("minutely_15")
        if not isinstance(block, dict) or "time" not in block:
            raise ExternalApiError(
                "open-meteo response missing 'minutely_15' block",
                provider=self.provider,
                detail={"keys": list(payload.keys())},
            )

        times = block["time"]
        temps = block.get("temperature_2m", [])
        hums = block.get("relative_humidity_2m", [])
        precs = block.get("precipitation", [])
        points = [
            {
                "time": t,
                "temperature": temps[i] if i < len(temps) else None,
                "humidity": hums[i] if i < len(hums) else None,
                "is_raining": (precs[i] if i < len(precs) else 0) > 0,
            }
            for i, t in enumerate(times)
            # 15분 포인트 중 정시·정각+30분만 채택 ("T07:00", "T07:30" 형태만 남김)
            if t.endswith(":00") or t.endswith(":30")
        ]
        logger.info(
            "weather forecast response",
            extra={"event": "weather_response", "detail": {"points": len(points)}},
        )
        return points
