# NYC Weather Adapter — Open-Meteo에서 뉴욕 현재 날씨를 가져온다.
# 학습 데이터(ml/train.py, 뉴욕 택시+날씨)와 같은 분포를 맞추기 위해 실제 서비스 지역(서울) 대신
# 뉴욕 좌표를 고정 사용한다 (실배포 없는 데모 전제 — zone 개념 없음).
import httpx

from common.core.exceptions import ExternalApiError
from common.core.logger import get_logger

logger = get_logger("nyc_weather_adapter")

# ml/preprocess.py의 NYC_LATITUDE/NYC_LONGITUDE와 동일 좌표
NYC_LATITUDE = 40.7128
NYC_LONGITUDE = -74.0060

_CURRENT_FIELDS = ["temperature_2m", "relative_humidity_2m", "precipitation"]


class NycWeatherAdapter:
    def __init__(self, base_url: str, timeout_seconds: float):
        self._base_url = base_url
        self._timeout = timeout_seconds

    def fetch_current(self) -> dict:
        """ml/features.py의 build_features(dt, temperature, humidity, is_raining) 입력 형태로 반환."""
        params = {
            "latitude": NYC_LATITUDE,
            "longitude": NYC_LONGITUDE,
            "current": ",".join(_CURRENT_FIELDS),
            "timezone": "America/New_York",
        }
        try:
            response = httpx.get(self._base_url, params=params, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ExternalApiError(
                f"open-meteo request failed: {exc}", provider="open-meteo"
            ) from exc

        current = payload.get("current")
        if not isinstance(current, dict):
            raise ExternalApiError(
                "open-meteo response missing 'current' block",
                provider="open-meteo",
                detail={"keys": list(payload.keys())},
            )

        precipitation = current.get("precipitation") or 0.0
        result = {
            "temperature": current.get("temperature_2m"),
            "humidity": current.get("relative_humidity_2m"),
            "is_raining": precipitation > 0,
        }
        logger.info(
            "nyc weather fetched",
            extra={"event": "nyc_weather_fetched", "detail": result},
        )
        return result
