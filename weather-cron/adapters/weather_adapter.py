# Weather Adapter 추상 인터페이스 — Service는 이 인터페이스만 의존한다.
# 기상청 API / WeatherAPI / OpenWeather 교체 시 구현체만 추가하면 된다.
from abc import ABC, abstractmethod


class WeatherAdapter(ABC):
    """외부 날씨 API 접근 계층. 반환값은 provider 중립 dict(raw)이며 Service가 검증/매핑한다."""

    provider: str = "unknown"

    @abstractmethod
    async def fetch_current(self, latitude: float, longitude: float) -> dict:
        """지정 좌표의 현재 날씨 원시 데이터를 반환한다.

        반환 dict 규약 (provider 중립):
          time(str, ISO), timezone(str),
          temperature_c, humidity_pct, rain_mm, precipitation_mm,
          wind_speed_kmh, cloud_cover_pct, weather_code, visibility_m (모두 nullable)
        실패 시 ExternalApiError를 발생시킨다.
        """
