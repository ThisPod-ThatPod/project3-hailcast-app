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


# NYC 좌표 — 학습 데이터(ml/preprocess.py)와 같은 지점을 써야 train-serve 분포가 맞는다.
NYC_LATITUDE = 40.7128
NYC_LONGITUDE = -74.0060

# weather-cron이 쓰고 predict가 읽는 FileStore 키 계약 — 두 서비스가 각자 config에서
# 이 값을 기본값으로 쓴다 (여전히 env로 개별 오버라이드 가능하지만 기본값은 항상 일치).
WEATHER_FORECAST_CSV_KEY = "weather/nyc-forecast.csv"

# --- A1: 트래픽 집계 계약 ---
# call-api 각 파드가 10초마다 자기 몫의 콜 수를 여기 써야 한다(파드마다 고유 파일 —
# 여러 파드가 동시에 써도 충돌 없음). predict가 이 prefix 밑 파일을 전부 모아 합산한다.
# 스키마: {"count": <최근 10초간 이 파드가 받은 콜 수>, "updated_at": <ISO8601>}
# (count=0이어도 매 주기 갱신해야 한다 — updated_at이 오래되면 죽은 파드로 보고
# 집계에서 제외되기 때문에, 살아있다는 신호로 하트비트처럼 계속 써야 한다.)
TRAFFIC_INSTANCE_PREFIX = "traffic/instances/"

# predict가 TRAFFIC_INSTANCE_PREFIX를 합산해서 쓰고, predict의 스케일러(G2)가 읽는다.
# hourly_requests = 최근 1시간 동안의 실제 콜 수 합계 — G1의 scaling_demand_per_pod와
# 같은 단위(시간당 수요)라 워터마크 비교가 바로 성립한다.
TRAFFIC_JSON_KEY = "dashboard/traffic.json"

# 10초 버킷별 원시 이력 — H2(트래픽 추이 그래프)가 여기서 원하는 구간만 골라 읽는다.
TRAFFIC_HISTORY_KEY = "dashboard/traffic-history.json"

# --- C: 콜 처리 상태 계약 ---
# worker가 처리한 콜마다 <call_id>.json 하나씩 쓰고, call-api의 GET /call/{id}가
# 같은 키로 읽는다 (common/models/call.py::CallStatusResponse 형태로 매핑).
CALL_RECORD_PREFIX = "calls/"

# --- A2: simulator 상태 계약 ---
# simulator(로컬 전용, 파드로 안 뜸)가 주기적으로 자기 상태(SimulatorStatus)를 여기 쓴다.
# predict/대시보드는 simulator 프로세스에 실시간 HTTP로 안 묻고 이 파일만 읽는다 — local
# 백엔드로 같은 개발 머신에서 두 프로세스가 로컬 디스크를 공유할 때만 의미가 있다
# (simulator는 원래 클라우드에 안 올라가는 로컬 도구라 s3 백엔드에서는 애초에 해당 없음).
SIMULATOR_STATUS_KEY = "simulator/status.json"

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
