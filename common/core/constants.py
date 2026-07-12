# 공통 상수 — 상태값·메시지 버전 등 매직넘버 금지 원칙
from enum import StrEnum


class CallStatus(StrEnum):
    QUEUED = "QUEUED"          # Call API가 SQS에 적재한 직후 (DB 저장 전)
    PROCESSING = "PROCESSING"  # Worker가 메시지를 집어 처리 중
    DONE = "DONE"              # DB 저장 + ACK 완료
    FAILED = "FAILED"          # 재시도 한도 초과


# SQS 메시지 스키마 버전 (역호환 파싱 대비)
MESSAGE_VERSION = "1"

# 콜 요청 출처 구분 (향후 ML feature)
SOURCE_API = "api"
SOURCE_SIMULATOR = "simulator"


# 서비스 구역 좌표 (zone_id → lat, lon)
# Weather 수집·Forecast 예측·수요 집계가 같은 zone_id 키로 Join된다.
ZONE_COORDINATES: dict[str, tuple[float, float]] = {
    "gangnam": (37.4979, 127.0276),
    "hongdae": (37.5563, 126.9236),
    "jongno": (37.5729, 126.9793),
    "yeouido": (37.5219, 126.9245),
    "jamsil": (37.5133, 127.1001),
    "itaewon": (37.5345, 126.9946),
    "seongsu": (37.5446, 127.0559),
    "mapo": (37.5638, 126.9084),
    "guro": (37.4954, 126.8874),
}


class WeatherDataType:
    """Weather 레코드 구분 — History(실측)와 Forecast(예보)를 같은 테이블에 저장."""

    CURRENT = "current"
    FORECAST = "forecast"
