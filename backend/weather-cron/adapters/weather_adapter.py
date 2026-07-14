# Weather Adapter 추상 인터페이스 — Service는 이 인터페이스만 의존한다.
# 기상청 API / WeatherAPI / OpenWeather 교체 시 구현체만 추가하면 된다.
from abc import ABC, abstractmethod


class WeatherAdapter(ABC):
    """외부 날씨 API 접근 계층. 반환값은 provider 중립 list[dict]이며 Service가 매핑한다."""

    provider: str = "unknown"

    @abstractmethod
    async def fetch_forecast(self, latitude: float, longitude: float, hours: int) -> list[dict]:
        """지정 좌표의 향후 hours시간 예보를 30분 간격(매 시 :00, :30)으로 반환한다.

        30분 간격인 이유: predict가 시간 버킷 하나(예: 01시)에 :00/:30 두 시점의 날씨로
        각각 예측해서 더 큰(악조건) 쪽을 그 시간의 대표값으로 쓴다 — 1시엔 안 오던 비가
        1시반에 온다면 파드 수는 비 오는 쪽 기준으로 잡아야 안전하기 때문.

        반환 리스트의 각 원소 (provider 중립):
          time(str, ISO, 요청 timezone 기준 로컬시각), temperature, humidity, is_raining(bool)
        실패 시 ExternalApiError를 발생시킨다.
        """
