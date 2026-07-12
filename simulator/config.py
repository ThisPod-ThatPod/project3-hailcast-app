# Simulator 설정 — Traffic 파라미터는 전부 환경변수 (매직넘버 금지)
from functools import lru_cache

from common.core.settings import BaseAppSettings


class SimulatorSettings(BaseAppSettings):
    service_name: str = "simulator"

    # --- 대상 ---
    call_api_url: str = "http://localhost:8000"   # 실제 Call API (Dummy API 금지)

    # --- Traffic 제어 (k6 서브프로세스, simulator/k6/call_load.js) ---
    traffic_step: float = 5.0        # increase/decrease 1회당 TPS 증감폭
    min_tps: float = 0.0             # 하한 (0 이하로 내려가지 않음, 0이면 k6 정지)
    max_tps: float = 200.0           # 상한 (Call API/로컬 환경 보호)
    k6_binary: str = "k6"            # PATH에 있는 k6 실행 파일명/경로

    # --- Status ---
    status_refresh_seconds: float = 1.0   # Frontend 폴링 권장 주기 (status 응답에 포함 가능)


@lru_cache
def get_settings() -> SimulatorSettings:
    return SimulatorSettings()
