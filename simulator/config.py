# Simulator 설정 — Traffic 파라미터는 전부 환경변수 (매직넘버 금지)
from functools import lru_cache

from common.core.settings import BaseAppSettings


class SimulatorSettings(BaseAppSettings):
    service_name: str = "simulator"

    # --- 대상 ---
    call_api_url: str = "http://localhost:8000"   # 실제 Call API (Dummy API 금지)
    request_timeout_seconds: float = 5.0

    # --- Traffic 제어 ---
    traffic_step: float = 5.0        # increase/decrease 1회당 TPS 증감폭
    min_tps: float = 0.0             # 하한 (0 이하로 내려가지 않음)
    max_tps: float = 200.0           # 상한 (Call API/로컬 환경 보호)
    generator_tick_seconds: float = 0.2   # Generator 루프 주기 — TPS 변경이 tick 단위로 즉시 반영
    max_in_flight: int = 100         # 동시 요청 상한 (백프레셔)

    # --- 데이터 생성 ---
    random_seed: int | None = None   # 지정 시 재현 가능한 트래픽 생성

    # --- Status ---
    status_refresh_seconds: float = 1.0   # Frontend 폴링 권장 주기 (status 응답에 포함 가능)


@lru_cache
def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
